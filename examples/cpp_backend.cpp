// Localhost-only C++17 dependency-free HTTP backend for TraceRoot instrumentation.
// One request per connection; this is a controlled experiment, not an HTTP library.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <time.h>

namespace {
uint64_t ns(clockid_t clock) {
    timespec ts{};
    if (clock_gettime(clock, &ts) != 0) throw std::runtime_error("clock failed");
    return uint64_t(ts.tv_sec) * 1000000000u + uint64_t(ts.tv_nsec);
}
struct Fd {
    int fd;
    explicit Fd(int f) : fd(f) {}
    ~Fd() { if (fd >= 0) close(fd); }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
};
bool trace_id_valid(const std::string& id) {
    if (id.empty() || id.size() > 80) return false;
    for (char c : id) if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                           (c >= '0' && c <= '9') || c == '-')) return false;
    return true;
}
uint32_t do_work(int milliseconds, uint64_t& cpu_ns) {
    const uint64_t start = ns(CLOCK_THREAD_CPUTIME_ID);
    // Prevent compiler from optimizing the arithmetic loop away.
    volatile uint32_t value = 0x12481248;
    do {
        for (int i = 0; i < 128; ++i)
            value = value * 1664525u + uint32_t(i) + 1013904223u;
    } while (ns(CLOCK_THREAD_CPUTIME_ID) - start < uint64_t(milliseconds) * 1000000u);
    cpu_ns = ns(CLOCK_THREAD_CPUTIME_ID) - start;
    return value;
}
void write_all(int fd, const std::string& data) {
    size_t sent = 0;
    while (sent < data.size()) {
        const ssize_t n = send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
        if (n <= 0) {
            if (n < 0 && errno == EINTR) continue;
            throw std::runtime_error("send failed");
        }
        sent += size_t(n);
    }
}
void reply(int fd, const std::string& body, int code = 200) {
    const std::string status = code == 200 ? "200 OK" : "400 Bad Request";
    const std::string header = "HTTP/1.1 " + status + "\r\nContent-Type: application/json\r\n" +
        "Content-Length: " + std::to_string(body.size()) + "\r\nConnection: close\r\n\r\n";
    write_all(fd, header + body);
}
void handle(int fd, int cpu_ms) {
    std::string req;
    char buffer[1024];
    while (req.find("\r\n\r\n") == std::string::npos && req.size() <= 4096) {
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n <= 0) return;
        req.append(buffer, size_t(n));
    }
    if (req.size() > 4096 || req.compare(0, 20, "GET /work HTTP/1.1\r\n") != 0) {
        reply(fd, "{\"error\":\"invalid_request\"}", 400); return;
    }
    const std::string header = "X-Trace-Id: ";
    const size_t at = req.find(header, 20);
    if (at == std::string::npos || at < 2 || req.compare(at - 2, 2, "\r\n") != 0) {
        reply(fd, "{\"error\":\"trace_header_missing\"}", 400); return;
    }
    const size_t begin = at + header.size();
    const size_t end = req.find("\r\n", begin);
    if (end == std::string::npos) { reply(fd, "{\"error\":\"bad_trace_id\"}", 400); return; }
    const std::string id = req.substr(begin, end - begin);
    if (!trace_id_valid(id)) { reply(fd, "{\"error\":\"bad_trace_id\"}", 400); return; }
    const auto begin_ns = ns(CLOCK_MONOTONIC);
    uint64_t cpu_ns = 0;
    const uint32_t checksum = do_work(cpu_ms, cpu_ns);
    const auto end_ns = ns(CLOCK_MONOTONIC);
    reply(fd, "{\"trace_id\":\"" + id + "\",\"start_ns\":" + std::to_string(begin_ns) +
              ",\"end_ns\":" + std::to_string(end_ns) + ",\"cpu_ns\":" +
              std::to_string(cpu_ns) + ",\"checksum\":" + std::to_string(checksum) + "}");
}
}
int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::invalid_argument("usage: cpp_backend CPU_MS (0..250)");
        const std::string arg = argv[1];
        size_t parsed = 0;
        const long ms = std::stol(arg, &parsed);
        if (parsed != arg.size() || ms < 0 || ms > 250) throw std::invalid_argument("invalid CPU_MS");
        Fd server(socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0));
        if (server.fd < 0) throw std::runtime_error("socket failed");
        sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_port = 0;
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (bind(server.fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0 ||
            listen(server.fd, 16) != 0) throw std::runtime_error("bind/listen failed");
        socklen_t size = sizeof(addr);
        if (getsockname(server.fd, reinterpret_cast<sockaddr*>(&addr), &size) != 0)
            throw std::runtime_error("getsockname failed");
        std::cout << "{\"port\":" << ntohs(addr.sin_port) << ",\"role\":\"backend\"}" << std::endl;
        for (;;) {
            Fd client(accept4(server.fd, nullptr, nullptr, SOCK_CLOEXEC));
            if (client.fd < 0) {
                if (errno == EINTR) continue;
                throw std::runtime_error("accept failed");
            }
            handle(client.fd, int(ms));
        }
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << '\n';
        return 2;
    }
}
