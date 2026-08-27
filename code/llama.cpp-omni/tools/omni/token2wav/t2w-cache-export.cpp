#include "token2wav-impl.h"

#include <cstdio>
#include <cstdlib>
#include <string>

// 用法: t2w-cache-export <token2wav-gguf目录> <prompt_bundle目录> <n_timesteps> <导出目录>
// 触发 init_from_prompt_bundle 的 setup_cache 并导出 prompt_cache.gguf（T2W_EXPORT_CACHE_DIR）
int main(int argc, char ** argv) {
    if (argc < 5) {
        std::fprintf(stderr, "usage: %s <model_dir> <bundle_dir> <n_timesteps> <export_dir>\n", argv[0]);
        return 2;
    }
    const std::string model_dir  = argv[1];
    const std::string bundle_dir = argv[2];
    const int         nt         = std::atoi(argv[3]);
    const std::string export_dir = argv[4];

    setenv("T2W_EXPORT_CACHE_DIR", export_dir.c_str(), 1);

    omni::flow::Token2WavSession sess;
    const std::string enc   = model_dir + "/encoder.gguf";
    const std::string flow  = model_dir + "/flow_matching.gguf";
    const std::string fextra = model_dir + "/flow_extra.gguf";
    const std::string voc   = model_dir + "/hifigan2.gguf";

    const bool ok = sess.init_from_prompt_bundle(enc, flow, fextra, bundle_dir, voc, "gpu", "gpu:0", nt, 1.0f, "");
    std::fprintf(stderr, "init_from_prompt_bundle n_timesteps=%d -> %s\n", nt, ok ? "OK" : "FAIL");
    return ok ? 0 : 3;
}
