// =============================================================================
// blender_cpp_hub — hub_core.cpp
// Copyright © 2025–2026 Eternal Path Media / D. Chow / Claude Sonnet / Llammy
//
// C++ core for the Blender SSMCP hub bridge.
// Compiled as a shared library (.dylib on macOS), loaded by the Blender
// Python add-on via ctypes.
//
// Responsibilities:
//   • Non-blocking TCP client to SSMCP hub (port 19999 HTTP + 19994 binary)
//   • Thread-safe ring buffer for animation frame data (bone matrices)
//   • Async command queue: recv hub commands, expose to Python poll
//   • Serialise/deserialise bone matrix arrays as raw float32 packets
//
// Build:
//   ./build.sh   (or see CMakeLists.txt)
// =============================================================================

#include <atomic>
#include <cstring>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

// POSIX sockets
#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

// C API — all symbols exported for ctypes
extern "C" {

// ─── Types ────────────────────────────────────────────────────────────────────

// 16 floats = 4x4 matrix
struct BoneMatrix {
    float m[16];
};

// One animation frame: N bones + metadata
struct FramePacket {
    uint32_t frame_number;
    uint32_t bone_count;
    double   timestamp;
    // bone data follows (variable length)
};

// ─── Ring buffer ─────────────────────────────────────────────────────────────

static const int RING_SIZE = 64;

struct RingBuffer {
    std::vector<std::vector<float>> frames;
    std::vector<uint32_t>           frame_nums;
    std::atomic<int>                head{0};
    std::atomic<int>                tail{0};
    std::mutex                      mtx;

    RingBuffer() : frames(RING_SIZE), frame_nums(RING_SIZE, 0) {}

    bool push(uint32_t fn, const float* data, int n_floats) {
        std::lock_guard<std::mutex> lk(mtx);
        int next = (head.load() + 1) % RING_SIZE;
        if (next == tail.load()) return false;  // full
        frames[head.load()].assign(data, data + n_floats);
        frame_nums[head.load()] = fn;
        head.store(next);
        return true;
    }

    bool pop(uint32_t* fn_out, std::vector<float>& data_out) {
        std::lock_guard<std::mutex> lk(mtx);
        if (head.load() == tail.load()) return false;  // empty
        *fn_out  = frame_nums[tail.load()];
        data_out = frames[tail.load()];
        tail.store((tail.load() + 1) % RING_SIZE);
        return true;
    }

    int size() {
        std::lock_guard<std::mutex> lk(mtx);
        return (head.load() - tail.load() + RING_SIZE) % RING_SIZE;
    }
};

// ─── Command queue ────────────────────────────────────────────────────────────

struct CommandQueue {
    std::deque<std::string> q;
    std::mutex              mtx;

    void push(const std::string& cmd) {
        std::lock_guard<std::mutex> lk(mtx);
        q.push_back(cmd);
    }

    bool pop(std::string& out) {
        std::lock_guard<std::mutex> lk(mtx);
        if (q.empty()) return false;
        out = q.front();
        q.pop_front();
        return true;
    }

    int size() {
        std::lock_guard<std::mutex> lk(mtx);
        return (int)q.size();
    }
};

// ─── Hub state ────────────────────────────────────────────────────────────────

static RingBuffer   g_ring;
static CommandQueue g_cmds;
static std::string  g_hub_host = "127.0.0.1";
static int          g_hub_port = 19999;
static int          g_bin_port = 19994;
static std::atomic<bool> g_running{false};
static std::thread  g_worker;
static char         g_last_error[512] = {0};
static std::atomic<uint64_t> g_frames_sent{0};
static std::atomic<uint64_t> g_cmds_recv{0};

// ─── HTTP helper (minimal, synchronous) ───────────────────────────────────────

static int _connect(const char* host, int port) {
    struct hostent* he = gethostbyname(host);
    if (!he) return -1;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    struct sockaddr_in sa{};
    sa.sin_family = AF_INET;
    sa.sin_port   = htons(port);
    memcpy(&sa.sin_addr, he->h_addr_list[0], he->h_length);
    struct timeval tv{2, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    if (connect(fd, (struct sockaddr*)&sa, sizeof(sa)) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static bool _http_post(const char* path, const char* body_json,
                        char* resp_buf, int resp_cap) {
    int fd = _connect(g_hub_host.c_str(), g_hub_port);
    if (fd < 0) {
        snprintf(g_last_error, sizeof(g_last_error), "connect failed: %s:%d", g_hub_host.c_str(), g_hub_port);
        return false;
    }
    int body_len = (int)strlen(body_json);
    char req[4096];
    int req_len = snprintf(req, sizeof(req),
        "POST %s HTTP/1.1\r\nHost: %s:%d\r\n"
        "Content-Type: application/json\r\nContent-Length: %d\r\n"
        "Connection: close\r\n\r\n%s",
        path, g_hub_host.c_str(), g_hub_port, body_len, body_json);
    send(fd, req, req_len, 0);
    int n = recv(fd, resp_buf, resp_cap - 1, 0);
    close(fd);
    if (n > 0) resp_buf[n] = 0;
    return n > 0;
}

// ─── Binary frame sender (UDP broadcast for lowest latency) ──────────────────
// Packet layout: [uint32 magic][uint32 frame_num][uint32 n_floats][float32...bones...]

static const uint32_t MAGIC = 0x45504D31u;  // "EPM1"

static bool _send_binary_frame(uint32_t frame_num, const float* data, int n_floats) {
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return false;
    struct sockaddr_in sa{};
    sa.sin_family = AF_INET;
    sa.sin_port   = htons(g_bin_port);
    inet_pton(AF_INET, g_hub_host.c_str(), &sa.sin_addr);

    int data_bytes = n_floats * sizeof(float);
    int pkt_len    = 12 + data_bytes;
    std::vector<uint8_t> pkt(pkt_len);
    uint32_t* hdr = reinterpret_cast<uint32_t*>(pkt.data());
    hdr[0] = MAGIC;
    hdr[1] = frame_num;
    hdr[2] = (uint32_t)n_floats;
    memcpy(pkt.data() + 12, data, data_bytes);

    sendto(fd, pkt.data(), pkt_len, 0, (struct sockaddr*)&sa, sizeof(sa));
    close(fd);
    return true;
}

// ─── Background flush worker ──────────────────────────────────────────────────

static void _worker_fn() {
    while (g_running.load()) {
        uint32_t fn;
        std::vector<float> data;
        while (g_ring.pop(&fn, data)) {
            _send_binary_frame(fn, data.data(), (int)data.size());
            g_frames_sent.fetch_add(1);
        }
        std::this_thread::sleep_for(std::chrono::microseconds(500));
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PUBLIC C API (ctypes-callable)
// ═══════════════════════════════════════════════════════════════════════════════

void hub_set_target(const char* host, int http_port, int bin_port) {
    g_hub_host = host;
    g_hub_port = http_port;
    g_bin_port = bin_port;
}

int hub_start() {
    if (g_running.load()) return 1;
    g_running.store(true);
    g_worker = std::thread(_worker_fn);
    return 0;
}

void hub_stop() {
    g_running.store(false);
    if (g_worker.joinable()) g_worker.join();
}

// Push a frame to the ring buffer (called from Blender frame_change handler).
// data = flat float32 array: [m00..m33, m00..m33, ...] — 16 floats per bone
int hub_push_frame(uint32_t frame_num, const float* bone_matrices, int n_bones) {
    int n = n_bones * 16;
    return g_ring.push(frame_num, bone_matrices, n) ? 0 : -1;
}

// Flush ring buffer immediately (sync, blocks until empty).
void hub_flush() {
    uint32_t fn;
    std::vector<float> data;
    while (g_ring.pop(&fn, data)) {
        _send_binary_frame(fn, data.data(), (int)data.size());
        g_frames_sent.fetch_add(1);
    }
}

// Send an SSMCP state payload via HTTP POST to the hub.
int hub_send_state(const char* key, const char* json_payload) {
    char body[8192];
    snprintf(body, sizeof(body),
             "{\"key\":\"%s\",\"payload\":%s,\"source\":\"blender_cpp_hub\"}", key, json_payload);
    char resp[4096];
    return _http_post("/ssmcp/state", body, resp, sizeof(resp)) ? 0 : -1;
}

// Send a chat message to a named sub-agent via the hub.
int hub_agent_chat(const char* agent, const char* message, char* out, int out_cap) {
    char body[4096];
    snprintf(body, sizeof(body),
             "{\"message\":\"%s\",\"stream\":false}", message);
    char path[128];
    snprintf(path, sizeof(path), "/agents/%s", agent);
    char resp[65536];
    if (!_http_post(path, body, resp, sizeof(resp))) {
        strncpy(out, g_last_error, out_cap - 1);
        return -1;
    }
    // Find JSON body after \r\n\r\n
    const char* body_start = strstr(resp, "\r\n\r\n");
    if (body_start) body_start += 4;
    else            body_start = resp;
    strncpy(out, body_start, out_cap - 1);
    out[out_cap - 1] = 0;
    return 0;
}

// Poll the command queue for incoming hub commands.
// Returns 1 if a command was available, 0 if empty.
int hub_poll_command(char* out, int out_cap) {
    std::string cmd;
    if (!g_cmds.pop(cmd)) return 0;
    strncpy(out, cmd.c_str(), out_cap - 1);
    out[out_cap - 1] = 0;
    g_cmds_recv.fetch_add(1);
    return 1;
}

void hub_stats(uint64_t* frames_sent, uint64_t* cmds_recv,
               int* ring_depth, int* cmd_depth) {
    *frames_sent = g_frames_sent.load();
    *cmds_recv   = g_cmds_recv.load();
    *ring_depth  = g_ring.size();
    *cmd_depth   = g_cmds.size();
}

const char* hub_last_error() {
    return g_last_error;
}

int hub_ping() {
    char resp[512];
    return _http_post("/sanctuary/status", "{}", resp, sizeof(resp)) ? 0 : -1;
}

}  // extern "C"
