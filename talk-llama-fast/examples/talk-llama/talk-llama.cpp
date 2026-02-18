// Talk with AI
//

#include "common-sdl.h"
#include "common.h"
#include "whisper.h"
#include "llama.h"

#include <cassert>
#include <cstdio>
#include <fstream>
#include <regex>
#include <string>
#include <thread>
#include <vector>
#include <regex>
#include <sstream>
#include <iostream>
#include <mutex>
#include <algorithm>
#include <cctype>

// For TTS communication
#include "tts-socket.h"
#include "tts-request.h"

// Async TTS to allow speech to interrupt response
//void send_tts_async(std::string text, std::string speaker_wav = "emma_1", std::string language = "en", std::string tts_url = "http://localhost:8020/", int reply_part = 0)
struct alpha_op {
    bool operator()(char c) {
        return std::isalpha(c);
    }
};

std::mutex tts_mutex;

void send_tts_async(std::string text)
{
	int hSocket, read_size;
    struct sockaddr_in server;

	// printf("send_tts_async: %s\n", text.c_str()); // debug

	if (text.size() >= 1 && text != "." && text != "," && text != "!" && text != "\n")
	{		
		bool contains_alpha = std::find_if(text.begin(), text.end(), alpha_op()) != text.end();
		// Don't bother with non-alpha text
		if(!contains_alpha)
		{
			printf("Command had no alpha\n");
			return;
		}

		trim(text);
		text = ::replace(text, "\r", "");
		text = ::replace(text, "\n", " ");
		text = ::replace(text, "\"", "");
		text = ::replace(text, "..", ".");
		
		char *json = TTS_RequestEncode(text.c_str());
		if(json == NULL)
		{
			printf("Error creating request\n");
			return;
		}
		// Lock mutex
		// tts_mutex.lock();

		//Create socket
		hSocket = TTS_SocketCreate();
		if(hSocket == -1)
		{
			printf("Could not create socket\n");
			return;
		}
		// printf("Socket is created\n");
		//Connect to remote server
		if (TTS_SocketConnect(hSocket) < 0)
		{
			perror("connect failed.\n");
			return;
		}
		// printf("Sucessfully conected with server\n");
		// printf("Sending request to server:\n");
		// printf("%s\n", json);
		// gets(SendToServer);
		//Send data to the server
		TTS_SocketSend(hSocket, json, strlen(json));

		free(json);

		// Unlock mutex
		// tts_mutex.unlock();
		//Received the data from the server
		// read_size = SocketReceive(hSocket, server_reply, 200);
		// printf("Server Response : %s\n\n",server_reply);
		close(hSocket);
		shutdown(hSocket,0);
		shutdown(hSocket,1);
		shutdown(hSocket,2);
	}
}


static std::vector<llama_token> llama_tokenize(struct llama_context * ctx, const std::string & text, bool add_bos) {
    auto * model = llama_get_model(ctx);

    // upper limit for the number of tokens
    int n_tokens = text.length() + add_bos;
    std::vector<llama_token> result(n_tokens);
    n_tokens = llama_tokenize(model, text.data(), text.length(), result.data(), result.size(), add_bos, false);
    if (n_tokens < 0) {
        result.resize(-n_tokens);
        int check = llama_tokenize(model, text.data(), text.length(), result.data(), result.size(), add_bos, false);
        GGML_ASSERT(check == -n_tokens);
    } else {
        result.resize(n_tokens);
    }
    return result;
}

static std::string llama_token_to_piece(const struct llama_context * ctx, llama_token token) {
    std::vector<char> result(8, 0);
    const int n_tokens = llama_token_to_piece(llama_get_model(ctx), token, result.data(), result.size(), 0, false);
    if (n_tokens < 0) {
        result.resize(-n_tokens);
        int check = llama_token_to_piece(llama_get_model(ctx), token, result.data(), result.size(), 0, false);
        GGML_ASSERT(check == -n_tokens);
    } else {
        result.resize(n_tokens);
    }

    return std::string(result.data(), result.size());
}

// command-line parameters
struct whisper_params {
    int32_t n_threads  = std::min(4, (int32_t) std::thread::hardware_concurrency());
    int32_t voice_ms   = 10000;
    int32_t capture_id = -1;
    int32_t max_tokens = 32;
    int32_t audio_ctx  = 0;
    int32_t n_gpu_layers = 999;

    float vad_thold  = 0.6f;
    float freq_thold = 100.0f;

    bool translate      = false;
    bool print_special  = false;
    bool print_energy   = false;
    bool no_timestamps  = true;
    bool verbose_prompt = false;
    bool use_gpu        = true;
    bool flash_attn     = false;

    std::string person      = "Georgi";
    std::string bot_name    = "LLaMA";
    std::string wake_cmd    = "";
    std::string heard_ok    = "";
    std::string language    = "en";
    std::string model_wsp   = "models/ggml-base.en.bin";
    std::string model_llama = "models/ggml-llama-7B.bin";
    std::string speak       = "./examples/talk-llama/speak";
    std::string speak_file  = "./examples/talk-llama/to_speak.txt";
    std::string prompt      = "";
    std::string fname_out;
    std::string path_session = "";       // path to file for saving/loading model eval state
	// Added
	int32_t n_predict = 64; // Max number of tokens to predict
	int sleep_before_xtts = 0; // ms to sleep before calling TTS
	float vad_start_thold = 0.000270f; // 0 to turn off, you can see your current energy_last (loudness level) when running with --print-energy param
	float vad_last_ms = 1250; // minimum slience after speech (ms)
};

void whisper_print_usage(int argc, char ** argv, const whisper_params & params);

static bool whisper_params_parse(int argc, char ** argv, whisper_params & params) {
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];

        if (arg == "-h" || arg == "--help") {
            whisper_print_usage(argc, argv, params);
            exit(0);
        }
        else if (arg == "-t"   || arg == "--threads")        { params.n_threads      = std::stoi(argv[++i]); }
        else if (arg == "-vms" || arg == "--voice-ms")       { params.voice_ms       = std::stoi(argv[++i]); }
        else if (arg == "-c"   || arg == "--capture")        { params.capture_id     = std::stoi(argv[++i]); }
        else if (arg == "-mt"  || arg == "--max-tokens")     { params.max_tokens     = std::stoi(argv[++i]); }
        else if (arg == "-ac"  || arg == "--audio-ctx")      { params.audio_ctx      = std::stoi(argv[++i]); }
        else if (arg == "-ngl" || arg == "--n-gpu-layers")   { params.n_gpu_layers   = std::stoi(argv[++i]); }
        else if (arg == "-vth" || arg == "--vad-thold")      { params.vad_thold      = std::stof(argv[++i]); }
        else if (arg == "-fth" || arg == "--freq-thold")     { params.freq_thold     = std::stof(argv[++i]); }
        else if (arg == "-tr"  || arg == "--translate")      { params.translate      = true; }
        else if (arg == "-ps"  || arg == "--print-special")  { params.print_special  = true; }
        else if (arg == "-pe"  || arg == "--print-energy")   { params.print_energy   = true; }
        else if (arg == "-vp"  || arg == "--verbose-prompt") { params.verbose_prompt = true; }
        else if (arg == "-ng"  || arg == "--no-gpu")         { params.use_gpu        = false; }
        else if (arg == "-fa"  || arg == "--flash-attn")     { params.flash_attn     = true; }
        else if (arg == "-p"   || arg == "--person")         { params.person         = argv[++i]; }
        else if (arg == "-bn"   || arg == "--bot-name")      { params.bot_name       = argv[++i]; }
        else if (arg == "--session")                         { params.path_session   = argv[++i]; }
        else if (arg == "-w"   || arg == "--wake-command")   { params.wake_cmd       = argv[++i]; }
        else if (arg == "-ho"  || arg == "--heard-ok")       { params.heard_ok       = argv[++i]; }
        else if (arg == "-l"   || arg == "--language")       { params.language       = argv[++i]; }
        else if (arg == "-mw"  || arg == "--model-whisper")  { params.model_wsp      = argv[++i]; }
        else if (arg == "-ml"  || arg == "--model-llama")    { params.model_llama    = argv[++i]; }
        else if (arg == "-s"   || arg == "--speak")          { params.speak          = argv[++i]; }
        else if (arg == "-sf"  || arg == "--speak-file")     { params.speak_file     = argv[++i]; }
        else if (arg == "--prompt-file")                     {
            std::ifstream file(argv[++i]);
            std::copy(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>(), back_inserter(params.prompt));
            if (params.prompt.back() == '\n') {
                params.prompt.pop_back();
            }
        }
        else if (arg == "-f"   || arg == "--file")          { params.fname_out     = argv[++i]; }
        else {
            fprintf(stderr, "error: unknown argument: %s\n", arg.c_str());
            whisper_print_usage(argc, argv, params);
            exit(0);
        }
    }

    return true;
}

void whisper_print_usage(int /*argc*/, char ** argv, const whisper_params & params) {
    fprintf(stderr, "\n");
    fprintf(stderr, "usage: %s [options]\n", argv[0]);
    fprintf(stderr, "\n");
    fprintf(stderr, "options:\n");
    fprintf(stderr, "  -h,       --help           [default] show this help message and exit\n");
    fprintf(stderr, "  -t N,     --threads N      [%-7d] number of threads to use during computation\n", params.n_threads);
    fprintf(stderr, "  -vms N,   --voice-ms N     [%-7d] voice duration in milliseconds\n",              params.voice_ms);
    fprintf(stderr, "  -c ID,    --capture ID     [%-7d] capture device ID\n",                           params.capture_id);
    fprintf(stderr, "  -mt N,    --max-tokens N   [%-7d] maximum number of tokens per audio chunk\n",    params.max_tokens);
    fprintf(stderr, "  -ac N,    --audio-ctx N    [%-7d] audio context size (0 - all)\n",                params.audio_ctx);
    fprintf(stderr, "  -ngl N,   --n-gpu-layers N [%-7d] number of layers to store in VRAM\n",           params.n_gpu_layers);
    fprintf(stderr, "  -vth N,   --vad-thold N    [%-7.2f] voice activity detection threshold\n",        params.vad_thold);
    fprintf(stderr, "  -fth N,   --freq-thold N   [%-7.2f] high-pass frequency cutoff\n",                params.freq_thold);
    fprintf(stderr, "  -tr,      --translate      [%-7s] translate from source language to english\n",   params.translate ? "true" : "false");
    fprintf(stderr, "  -ps,      --print-special  [%-7s] print special tokens\n",                        params.print_special ? "true" : "false");
    fprintf(stderr, "  -pe,      --print-energy   [%-7s] print sound energy (for debugging)\n",          params.print_energy ? "true" : "false");
    fprintf(stderr, "  -vp,      --verbose-prompt [%-7s] print prompt at start\n",                       params.verbose_prompt ? "true" : "false");
    fprintf(stderr, "  -ng,      --no-gpu         [%-7s] disable GPU\n",                                 params.use_gpu ? "false" : "true");
    fprintf(stderr, "  -fa,      --flash-attn     [%-7s] flash attention\n",                             params.flash_attn ? "true" : "false");
    fprintf(stderr, "  -p NAME,  --person NAME    [%-7s] person name (for prompt selection)\n",          params.person.c_str());
    fprintf(stderr, "  -bn NAME, --bot-name NAME  [%-7s] bot name (to display)\n",                       params.bot_name.c_str());
    fprintf(stderr, "  -w TEXT,  --wake-command T [%-7s] wake-up command to listen for\n",               params.wake_cmd.c_str());
    fprintf(stderr, "  -ho TEXT, --heard-ok TEXT  [%-7s] said by TTS before generating reply\n",         params.heard_ok.c_str());
    fprintf(stderr, "  -l LANG,  --language LANG  [%-7s] spoken language\n",                             params.language.c_str());
    fprintf(stderr, "  -mw FILE, --model-whisper  [%-7s] whisper model file\n",                          params.model_wsp.c_str());
    fprintf(stderr, "  -ml FILE, --model-llama    [%-7s] llama model file\n",                            params.model_llama.c_str());
    fprintf(stderr, "  -s FILE,  --speak TEXT     [%-7s] command for TTS\n",                             params.speak.c_str());
    fprintf(stderr, "  -sf FILE, --speak-file     [%-7s] file to pass to TTS\n",                         params.speak_file.c_str());
    fprintf(stderr, "  --prompt-file FNAME        [%-7s] file with custom prompt to start dialog\n",     "");
    fprintf(stderr, "  --session FNAME                   file to cache model state in (may be large!) (default: none)\n");
    fprintf(stderr, "  -f FNAME, --file FNAME     [%-7s] text output file name\n",                       params.fname_out.c_str());
    fprintf(stderr, "\n");
}

static std::string transcribe(
        whisper_context * ctx,
        const whisper_params & params,
        const std::vector<float> & pcmf32,
        const std::string prompt_text,
        float & prob,
        int64_t & t_ms) {
    const auto t_start = std::chrono::high_resolution_clock::now();

    prob = 0.0f;
    t_ms = 0;

    std::vector<whisper_token> prompt_tokens;

    whisper_full_params wparams = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);

    prompt_tokens.resize(1024);
    prompt_tokens.resize(whisper_tokenize(ctx, prompt_text.c_str(), prompt_tokens.data(), prompt_tokens.size()));

    wparams.print_progress   = false;
    wparams.print_special    = params.print_special;
    wparams.print_realtime   = false;
    wparams.print_timestamps = !params.no_timestamps;
    wparams.translate        = params.translate;
    wparams.no_context       = true;
    wparams.single_segment   = true;
    wparams.max_tokens       = params.max_tokens;
    wparams.language         = params.language.c_str();
    wparams.n_threads        = params.n_threads;

    wparams.prompt_tokens    = prompt_tokens.empty() ? nullptr : prompt_tokens.data();
    wparams.prompt_n_tokens  = prompt_tokens.empty() ? 0       : prompt_tokens.size();

    wparams.audio_ctx        = params.audio_ctx;

    if (whisper_full(ctx, wparams, pcmf32.data(), pcmf32.size()) != 0) {
        return "";
    }

    int prob_n = 0;
    std::string result;

    const int n_segments = whisper_full_n_segments(ctx);
    for (int i = 0; i < n_segments; ++i) {
        const char * text = whisper_full_get_segment_text(ctx, i);

        result += text;

        const int n_tokens = whisper_full_n_tokens(ctx, i);
        for (int j = 0; j < n_tokens; ++j) {
            const auto token = whisper_full_get_token_data(ctx, i, j);

            prob += token.p;
            ++prob_n;
        }
    }

    if (prob_n > 0) {
        prob /= prob_n;
    }

    const auto t_end = std::chrono::high_resolution_clock::now();
    t_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t_end - t_start).count();

    return result;
}

static std::vector<std::string> get_words(const std::string &txt) {
    std::vector<std::string> words;

    std::istringstream iss(txt);
    std::string word;
    while (iss >> word) {
        words.push_back(word);
    }

    return words;
}

const std::string k_prompt_whisper = R"(A conversation with a person called {1}.)";

const std::string k_prompt_llama = R"(Text transcript of a never ending dialog, where {0} interacts with an AI assistant named {1}.
{1} is helpful, kind, honest, friendly, good at writing and never fails to answer {0}’s requests immediately and with details and precision.
There are no annotations like (30 seconds passed...) or (to himself), just what {0} and {1} say aloud to each other.
The transcript only includes text, it does not include markup like HTML and Markdown.
{1} responds with short and concise answers.

{0}{4} Hello, {1}!
{1}{4} Hello {0}! How may I help you today?
{0}{4} What time is it?
{1}{4} It is {2} o'clock.
{0}{4} What year is it?
{1}{4} We are in {3}.
{0}{4} What is a cat?
{1}{4} A cat is a domestic species of small carnivorous mammal. It is the only domesticated species in the family Felidae.
{0}{4} Name a color.
{1}{4} Blue
{0}{4})";

int main(int argc, char ** argv) {
    whisper_params params;

	std::vector<std::thread> threads;
	std::thread t;
	int thread_i = 0;
	int reply_part = 0;
	std::string text_to_speak_arr[150];
	int reply_part_arr[150];

    if (whisper_params_parse(argc, argv, params) == false) {
        return 1;
    }

    if (params.language != "auto" && whisper_lang_id(params.language.c_str()) == -1) {
        fprintf(stderr, "error: unknown language '%s'\n", params.language.c_str());
        whisper_print_usage(argc, argv, params);
        exit(0);
    }

    // whisper init

    struct whisper_context_params cparams = whisper_context_default_params();

    cparams.use_gpu    = params.use_gpu;
    cparams.flash_attn = params.flash_attn;

    struct whisper_context * ctx_wsp = whisper_init_from_file_with_params(params.model_wsp.c_str(), cparams);
    if (!ctx_wsp) {
        fprintf(stderr, "No whisper.cpp model specified. Please provide using -mw <modelfile>\n");
        return 1;
    }

    // llama init

    llama_backend_init();

    auto lmparams = llama_model_default_params();
    if (!params.use_gpu) {
        lmparams.n_gpu_layers = 0;
    } else {
        lmparams.n_gpu_layers = params.n_gpu_layers;
    }

    struct llama_model * model_llama = llama_load_model_from_file(params.model_llama.c_str(), lmparams);
    if (!model_llama) {
        fprintf(stderr, "No llama.cpp model specified. Please provide using -ml <modelfile>\n");
        return 1;
    }

    llama_context_params lcparams = llama_context_default_params();

    // tune these to your liking
    lcparams.n_ctx      = 2048;
    lcparams.seed       = 1;
    lcparams.n_threads  = params.n_threads;
    lcparams.flash_attn = params.flash_attn;

    struct llama_context * ctx_llama = llama_new_context_with_model(model_llama, lcparams);

    // print some info about the processing
    {
        fprintf(stderr, "\n");

        if (!whisper_is_multilingual(ctx_wsp)) {
            if (params.language != "en" || params.translate) {
                params.language = "en";
                params.translate = false;
                fprintf(stderr, "%s: WARNING: model is not multilingual, ignoring language and translation options\n", __func__);
            }
        }
        fprintf(stderr, "%s: processing, %d threads, lang = %s, task = %s, timestamps = %d ...\n",
                __func__,
                params.n_threads,
                params.language.c_str(),
                params.translate ? "translate" : "transcribe",
                params.no_timestamps ? 0 : 1);

        fprintf(stderr, "\n");
    }

    // init audio

    audio_async audio(30*1000);
    if (!audio.init(params.capture_id, WHISPER_SAMPLE_RATE)) {
        fprintf(stderr, "%s: audio.init() failed!\n", __func__);
        return 1;
    }

    audio.resume();

    bool is_running  = true;
    bool force_speak = false;

    float prob0 = 0.0f;

    const std::string chat_symb = ":";

    std::vector<float> pcmf32_cur;
    std::vector<float> pcmf32_prompt;

    const std::string prompt_whisper = ::replace(k_prompt_whisper, "{1}", params.bot_name);

    // construct the initial prompt for LLaMA inference
    std::string prompt_llama = params.prompt.empty() ? k_prompt_llama : params.prompt;

    // need to have leading ' '
    prompt_llama.insert(0, 1, ' ');

    prompt_llama = ::replace(prompt_llama, "{0}", params.person);
    prompt_llama = ::replace(prompt_llama, "{1}", params.bot_name);

    {
        // get time string
        std::string time_str;
        {
            time_t t = time(0);
            struct tm * now = localtime(&t);
            char buf[128];
            strftime(buf, sizeof(buf), "%H:%M", now);
            time_str = buf;
        }
        prompt_llama = ::replace(prompt_llama, "{2}", time_str);
    }

    {
        // get year string
        std::string year_str;
        {
            time_t t = time(0);
            struct tm * now = localtime(&t);
            char buf[128];
            strftime(buf, sizeof(buf), "%Y", now);
            year_str = buf;
        }
        prompt_llama = ::replace(prompt_llama, "{3}", year_str);
    }

    prompt_llama = ::replace(prompt_llama, "{4}", chat_symb);

    llama_batch batch = llama_batch_init(llama_n_ctx(ctx_llama), 0, 1);


    // init sampler
    const float top_k = 5;
    const float top_p = 0.80f;
    const float temp  = 0.30f;

    const int seed = 0;

    // auto sparams = llama_sampler_chain_default_params();

    // llama_sampler * smpl = llama_sampler_chain_init(sparams);

    // if (temp > 0.0f) {
    //     llama_sampler_chain_add(smpl, llama_sampler_init_top_k(top_k));
    //     llama_sampler_chain_add(smpl, llama_sampler_init_top_p(top_p, 1));
    //     llama_sampler_chain_add(smpl, llama_sampler_init_temp (temp));
    //     llama_sampler_chain_add(smpl, llama_sampler_init_dist (seed));
    // } else {
    //     llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    // }

    // init session
    std::string path_session = params.path_session;
    std::vector<llama_token> session_tokens;
    auto embd_inp = ::llama_tokenize(ctx_llama, prompt_llama, true);

    if (!path_session.empty()) {
        fprintf(stderr, "%s: attempting to load saved session from %s\n", __func__, path_session.c_str());

        // fopen to check for existing session
        FILE * fp = std::fopen(path_session.c_str(), "rb");
        if (fp != NULL) {
            std::fclose(fp);

            session_tokens.resize(llama_n_ctx(ctx_llama));
            size_t n_token_count_out = 0;
            if (!llama_state_load_file(ctx_llama, path_session.c_str(), session_tokens.data(), session_tokens.capacity(), &n_token_count_out)) {
                fprintf(stderr, "%s: error: failed to load session file '%s'\n", __func__, path_session.c_str());
                return 1;
            }
            session_tokens.resize(n_token_count_out);
            for (size_t i = 0; i < session_tokens.size(); i++) {
                embd_inp[i] = session_tokens[i];
            }

            fprintf(stderr, "%s: loaded a session with prompt size of %d tokens\n", __func__, (int) session_tokens.size());
        } else {
            fprintf(stderr, "%s: session file does not exist, will create\n", __func__);
        }
    }

    // evaluate the initial prompt

    printf("\n");
    printf("%s : initializing - please wait ...\n", __func__);

    // prepare batch
    {
        batch.n_tokens = embd_inp.size();

        for (int i = 0; i < batch.n_tokens; i++) {
            batch.token[i]     = embd_inp[i];
            batch.pos[i]       = i;
            batch.n_seq_id[i]  = 1;
            batch.seq_id[i][0] = 0;
            batch.logits[i]    = i == batch.n_tokens - 1;
        }
    }

    if (llama_decode(ctx_llama, batch)) {
        fprintf(stderr, "%s : failed to decode\n", __func__);
        return 1;
    }

    if (params.verbose_prompt) {
        fprintf(stdout, "\n");
        fprintf(stdout, "%s", prompt_llama.c_str());
        fflush(stdout);
    }

     // debug message about similarity of saved session, if applicable
    size_t n_matching_session_tokens = 0;
    if (session_tokens.size()) {
        for (llama_token id : session_tokens) {
            if (n_matching_session_tokens >= embd_inp.size() || id != embd_inp[n_matching_session_tokens]) {
                break;
            }
            n_matching_session_tokens++;
        }
        if (n_matching_session_tokens >= embd_inp.size()) {
            fprintf(stderr, "%s: session file has exact match for prompt!\n", __func__);
        } else if (n_matching_session_tokens < (embd_inp.size() / 2)) {
            fprintf(stderr, "%s: warning: session file has low similarity to prompt (%zu / %zu tokens); will mostly be reevaluated\n",
                __func__, n_matching_session_tokens, embd_inp.size());
        } else {
            fprintf(stderr, "%s: session file matches %zu / %zu tokens of prompt\n",
                __func__, n_matching_session_tokens, embd_inp.size());
        }
    }

    // HACK - because session saving incurs a non-negligible delay, for now skip re-saving session
    // if we loaded a session with at least 75% similarity. It's currently just used to speed up the
    // initial prompt so it doesn't need to be an exact match.
    bool need_to_save_session = !path_session.empty() && n_matching_session_tokens < (embd_inp.size() * 3 / 4);

    printf("%s : done! start speaking in the microphone\n", __func__);

    // show wake command if enabled
    const std::string wake_cmd = params.wake_cmd;
    const int wake_cmd_length = get_words(wake_cmd).size();
    const bool use_wake_cmd = wake_cmd_length > 0;

	int llama_interrupted = 0;

    if (use_wake_cmd) {
        printf("%s : the wake-up command is: '%s%s%s'\n", __func__, "\033[1m", wake_cmd.c_str(), "\033[0m");
    }

    printf("\n");
    printf("%s%s", params.person.c_str(), chat_symb.c_str());
    fflush(stdout);

    // clear audio buffer
    audio.clear();

    // text inference variables
    const int voice_id = 2;
    const int n_keep   = embd_inp.size();
    const int n_ctx    = llama_n_ctx(ctx_llama);

    int n_past = n_keep;
    int n_prev = 64; // TODO arg
    int n_session_consumed = !path_session.empty() && session_tokens.size() > 0 ? session_tokens.size() : 0;

    std::vector<llama_token> embd;

    // reverse prompts for detecting when it's time to stop speaking
    std::vector<std::string> antiprompts = {
        params.person + chat_symb,
    };

    // main loop
    while (is_running) {
        // handle Ctrl + C
        is_running = sdl_poll_events();

        if (!is_running) {
            break;
        }

        // delay
        std::this_thread::sleep_for(std::chrono::milliseconds(100));

        int64_t t_ms = 0;

        {
            audio.get(2000, pcmf32_cur);

            if (::vad_simple(pcmf32_cur, WHISPER_SAMPLE_RATE, 1250, params.vad_thold, params.freq_thold, params.print_energy) || force_speak) {
                //fprintf(stdout, "%s: Speech detected! Processing ...\n", __func__);

                audio.get(params.voice_ms, pcmf32_cur);

                std::string all_heard;

                if (!force_speak) {
                    all_heard = ::trim(::transcribe(ctx_wsp, params, pcmf32_cur, prompt_whisper, prob0, t_ms));
                }

                const auto words = get_words(all_heard);

                std::string wake_cmd_heard;
                std::string text_heard;

                for (int i = 0; i < (int) words.size(); ++i) {
                    if (i < wake_cmd_length) {
                        wake_cmd_heard += words[i] + " ";
                    } else {
                        text_heard += words[i] + " ";
                    }
                }

                // check if audio starts with the wake-up command if enabled
                if (use_wake_cmd) {
                    const float sim = similarity(wake_cmd_heard, wake_cmd);

                    if ((sim < 0.7f) || (text_heard.empty())) {
                        audio.clear();
                        continue;
                    }
                }

                // optionally give audio feedback that the current text is being processed
                if (!params.heard_ok.empty()) {
                    speak_with_file(params.speak, params.heard_ok, params.speak_file, voice_id);
                }

                // remove text between brackets using regex
                {
                    std::regex re("\\[.*?\\]");
                    text_heard = std::regex_replace(text_heard, re, "");
                }

                // remove text between brackets using regex
                {
                    std::regex re("\\(.*?\\)");
                    text_heard = std::regex_replace(text_heard, re, "");
                }

                // remove all characters, except for letters, numbers, punctuation and ':', '\'', '-', ' '
                text_heard = std::regex_replace(text_heard, std::regex("[^a-zA-Z0-9\\.,\\?!\\s\\:\\'\\-]"), "");

                // take first line
                text_heard = text_heard.substr(0, text_heard.find_first_of('\n'));

                // remove leading and trailing whitespace
                text_heard = std::regex_replace(text_heard, std::regex("^\\s+"), "");
                text_heard = std::regex_replace(text_heard, std::regex("\\s+$"), "");

				// Handle stop command
				if (text_heard == "stop" || text_heard.find("stop") != std::string::npos || text_heard.find("Stop") != std::string::npos)
				{
					printf(" [Stopped!]\n");
					text_heard = "";
					audio.clear();
					continue;
				}                
				
				const std::vector<llama_token> tokens = llama_tokenize(ctx_llama, text_heard.c_str(), false);

                if (text_heard.empty() || tokens.empty() || force_speak) {
                    //fprintf(stdout, "%s: Heard nothing, skipping ...\n", __func__);
                    audio.clear();

                    continue;
                }

                force_speak = false;

                text_heard.insert(0, 1, ' ');
                text_heard += "\n" + params.bot_name + chat_symb;
                fprintf(stdout, "%s%s%s", "\033[1m", text_heard.c_str(), "\033[0m");
                fflush(stdout);

                embd = ::llama_tokenize(ctx_llama, text_heard, false);

                // Append the new input tokens to the session_tokens vector
                if (!path_session.empty()) {
                    session_tokens.insert(session_tokens.end(), tokens.begin(), tokens.end());
                }
				// removing all threads
				// if (threads.size() >= 80) // check text_to_speak_arr init size 150
				// {
					// printf("[!...", threads.size());
					// for (auto &t : threads)
					// {
					// 	try
					// 	{
					// 		if (t.joinable())
					// 			t.join();
					// 		else
					// 			printf("Notice: thread %d is NOT joinable\n", thread_i);
					// 	}
					// 	catch (const std::exception &ex)
					// 	{
					// 		std::cerr << "[Exception]: Failed join a thread: " << ex.what() << '\n';
					// 	}
					// }
					// threads.clear();
					// printf("]");
				// }
				// if (thread_i > 100)
				// 	thread_i = 0; // rotation

                // text inference
                bool done = false;
                std::string text_to_speak;
				int new_tokens = 0;
				while (true)
				{
					// predict
					if (new_tokens > params.n_predict)
						break; // 64 default
					new_tokens++;
					if (embd.size() > 0) 
					{
                        if (n_past + (int) embd.size() > n_ctx) 
						{
                            n_past = n_keep;

                            // insert n_left/2 tokens at the start of embd from last_n_tokens
                            embd.insert(embd.begin(), embd_inp.begin() + embd_inp.size() - n_prev, embd_inp.end());
                            // stop saving session if we run out of context
                            path_session = "";
                            // printf("\n---\n");
                            // printf("resetting: '");
                            // for (int i = 0; i < (int) embd.size(); i++) {
                            //    printf("%s", llama_token_to_piece(ctx_llama, embd[i]));
                            // }
                            // printf("'\n");
                            // printf("\n---\n");
                        }

                        // try to reuse a matching prefix from the loaded session instead of re-eval (via n_past)
                        // REVIEW
                        if (n_session_consumed < (int) session_tokens.size()) 
						{
                            size_t i = 0;
                            for ( ; i < embd.size(); i++) {
                                if (embd[i] != session_tokens[n_session_consumed]) {
                                    session_tokens.resize(n_session_consumed);
                                    break;
                                }

                                n_past++;
                                n_session_consumed++;

                                if (n_session_consumed >= (int) session_tokens.size()) {
                                    i++;
                                    break;
                                }
                            }
                            if (i > 0) {
                                embd.erase(embd.begin(), embd.begin() + i);
                            }
                        }

                        if (embd.size() > 0 && !path_session.empty()) {
                            session_tokens.insert(session_tokens.end(), embd.begin(), embd.end());
                            n_session_consumed = session_tokens.size();
                        }

                        // prepare batch
                        {
                            batch.n_tokens = embd.size();

                            for (int i = 0; i < batch.n_tokens; i++) {
                                batch.token[i]     = embd[i];
                                batch.pos[i]       = n_past + i;
                                batch.n_seq_id[i]  = 1;
                                batch.seq_id[i][0] = 0;
                                batch.logits[i]    = i == batch.n_tokens - 1;
                            }
                        }
						printf("Calling llama_decode on %d tokens\n", batch.n_tokens);
                        if (llama_decode(ctx_llama, batch)) {
                            fprintf(stderr, "%s : failed to decode\n", __func__);
                            return 1;
                        }
                    }


                    embd_inp.insert(embd_inp.end(), embd.begin(), embd.end());
                    n_past += embd.size();

                    embd.clear();

                    if (done) 
						break;

                    {
                        // out of user input, sample next token
                        // const float top_k          = 5;
                        // const float top_p          = 0.80f;
                        // const float temp           = 0.30f;
                        const float repeat_penalty = 1.1764f;
                        const int repeat_last_n    = 256;

                        if (!path_session.empty() && need_to_save_session) 
						{
                            need_to_save_session = false;
                            llama_state_save_file(ctx_llama, path_session.c_str(), session_tokens.data(), session_tokens.size());
                        }

						llama_token id = 0;

                        {
                            auto logits = llama_get_logits(ctx_llama);
                            auto n_vocab = llama_n_vocab(model_llama);

                            logits[llama_token_eos(model_llama)] = 0;

                            std::vector<llama_token_data> candidates;
                            candidates.reserve(n_vocab);
                            for (llama_token token_id = 0; token_id < n_vocab; token_id++) {
                                candidates.emplace_back(llama_token_data{token_id, logits[token_id], 0.0f});
                            }

                            llama_token_data_array candidates_p = { candidates.data(), candidates.size(), false };

                            // apply repeat penalty
                            const float nl_logit = logits[llama_token_nl(model_llama)];

                            llama_sample_repetition_penalties(ctx_llama, &candidates_p,
                                    embd_inp.data() + std::max(0, n_past - repeat_last_n),
                                    repeat_last_n, repeat_penalty, 0.0, 0.0f);

                            logits[llama_token_nl(model_llama)] = nl_logit;

                            if (temp <= 0) {
                                // Greedy sampling
                                id = llama_sample_token_greedy(ctx_llama, &candidates_p);
                            } else {
                                // Temperature sampling
                                llama_sample_top_k(ctx_llama, &candidates_p, top_k, 1);
                                llama_sample_top_p(ctx_llama, &candidates_p, top_p, 1);
                                llama_sample_temp (ctx_llama, &candidates_p, temp);
                                id = llama_sample_token(ctx_llama, &candidates_p);
                            }
                        }

                        if (id != llama_token_eos(model_llama)) 
						{
                            // add it to the context
                            embd.push_back(id);

                            text_to_speak += llama_token_to_piece(ctx_llama, id);

                            printf("%s", llama_token_to_piece(ctx_llama, id).c_str());
                            fflush(stdout);
                        
                    

                    		// STOP on speech for llama, every 2 tokens
							if (new_tokens % 2 == 0)
							{
								// check energy level, if user is speaking (it doesn't call whisper recognition, just a loud noise will stop everything)
								audio.get(2000, pcmf32_cur); // non-blocking, 2000 step_ms
								int vad_result = ::vad_simple_int(pcmf32_cur, WHISPER_SAMPLE_RATE, params.vad_last_ms, params.vad_thold, params.freq_thold, params.print_energy, params.vad_start_thold);

								if (vad_result == 1) // || g_hotkey_pressed == "Ctrl+Space" || g_hotkey_pressed == "Alt") // speech started
								{
									llama_interrupted = 1;
									//llama_interrupted_time = get_current_time_ms();
									printf(" [Speech/Stop!]\n");
									done = true; // llama generation stop
									// g_hotkey_pressed = "";
									break;
								}
							}
							//	clear mic
							if (new_tokens == 20 && !llama_interrupted)
							{
								audio.clear();
								// printf("\n [audio cleared after 20t]\n");
							}
							// splitting for tts
							int text_len = text_to_speak.size();
							

							if (text_len >= 2 && new_tokens >= 2) // was 2 tokens && !person_name_is_found && ((new_tokens == split_after && params.split_after && text_to_speak[text_len - 1] != '\'') || text_to_speak[text_len - 1] == '.' || text_to_speak[text_len - 1] == '(' || text_to_speak[text_len - 1] == ')' || (text_to_speak[text_len - 1] == ',' && n_comas == 1 && new_tokens > split_after && params.split_after) || (text_to_speak[text_len - 2] == ' ' && text_to_speak[text_len - 1] == '-') || text_to_speak[text_len - 1] == '?' || text_to_speak[text_len - 1] == '!' || text_to_speak[text_len - 1] == ';' || text_to_speak[text_len - 1] == ':' || text_to_speak[text_len - 1] == '\n'))
							{
#if 0
								if (translation_is_going == 1)
								{
									translation_full += text_to_speak;
									// fprintf(stdout, " translation_full: (%s)\n", translation_full.c_str());
								}
#endif
								// fprintf(stdout, " split_sign: (%c), translation_is_going: %d\n", text_to_speak[text_len-1], translation_is_going);
								text_to_speak = ::replace(text_to_speak, "\"", "'");
								text_to_speak = ::replace(text_to_speak, antiprompts[0], "");

								if (text_to_speak.size()) // first and mid parts of the sentence
								{
									// system TTS
									// int ret = system(("start /B "+params.speak + " " + std::to_string(voice_id) + " \"" + text_to_speak + "\" & exit").c_str()); // for windows
									// int ret = system((params.speak + " " + std::to_string(voice_id) + " \"" + text_to_speak + "\" &").c_str()); // for linux

#if 0
									// translate
									// each generated sentence is translated by the same llama model, in the same ctx
									if (params.translate)
									{
										if (translation_is_going == 0)
										{
											std::string text_to_speak_translated = "";
											n_embd_inp_before_trans = embd_inp.size();
											fprintf(stdout, "\n	Перевод:", n_embd_inp_before_trans);
											std::string trans_prompt = "\nПеревод последнего предложения на русский.\n" + bot_name_current_ru + ":" + translation_full;
											// fprintf(stdout, "%s", trans_prompt.c_str());
											std::vector<llama_token> trans_prompt_emb = ::llama_tokenize(ctx_llama, trans_prompt, false); // prompt to tokens
											embd.insert(embd.end(), trans_prompt_emb.begin(), trans_prompt_emb.end());					  // inject prompt
											translation_is_going = 1;																	  // started
											text_to_speak = "";
											// fprintf(stdout, " translation_is_going: 0->1\n");
											continue;
										}
									}
#endif
									// XTTS in threads
									// text_to_speak_arr[thread_i] = text_to_speak;
									// reply_part_arr[thread_i] = reply_part;
									// reply_part++;
									// try
									// {
									// 	threads.emplace_back([&] // creates a thread, threads are cleaned after user ends speech, after 80 threads
									// 						 {
									// 		if (text_to_speak_arr[thread_i-1].size())
									// 		{
												// send_tts_async(text_to_speak_arr[thread_i-1]); //, current_voice, params.language, params.xtts_url, reply_part_arr[thread_i-1]);
												send_tts_async(text_to_speak); //, current_voice, params.language, params.xtts_url, reply_part_arr[thread_i-1]);
												// text_to_speak_arr[thread_i-1] = "";
												// reply_part_arr[thread_i-1] = 0;
										// 	} }
										// );
										// thread_i++;
										text_to_speak = "";
										// new_tokens = 0; // debug
										// if (params.sleep_before_xtts)
										// 	std::this_thread::sleep_for(std::chrono::milliseconds(params.sleep_before_xtts)); // 1s pause to speed up xtts/wav2lip inference

										// check energy level, if user is speaking (it doesn't call whisper recognition, just a loud noise will stop everything)
										// No hotkeys of push to talk
										// if (!params.push_to_talk || params.push_to_talk && g_hotkey_pressed == "Alt")
										{
											audio.get(2000, pcmf32_cur); // non-blocking, 2000 step_ms
											int vad_result = ::vad_simple_int(pcmf32_cur, WHISPER_SAMPLE_RATE, params.vad_last_ms, params.vad_thold, params.freq_thold, params.print_energy, params.vad_start_thold);
											if (vad_result == 1) // speech started
											{
												llama_interrupted = 1;
												// llama_interrupted_time = get_current_time_ms();
												printf(" [Speech!]\n");
												done = true; // llama generation stop
												break;
											}
										}
									// }
									// catch (const std::exception &ex)
									// {
									// 	std::cerr << "[Exception]: Failed to push_back mid thread: " << ex.what() << '\n';
									// }
#if 0
									// deleting translation from ctx
									if (params.translate && translation_is_going == 1)
									{
										translation_is_going = 0; // finished
										// fprintf(stdout, " translation_is_going 1->0 \n");

										if (n_embd_inp_before_trans && embd_inp.size())
										{
											int rollback_num = embd_inp.size() - n_embd_inp_before_trans;
											if (rollback_num)
											{
												embd_inp.erase(embd_inp.end() - rollback_num, embd_inp.end());
												n_past -= rollback_num;
												// printf(" deleting %d tokens. embd_inp: %d \n", rollback_num, embd_inp.size());
												printf("\n"); // to separate translation from original
											}
											continue;
										}
									}
#endif
								}
							}
						}
					}

					{
                        std::string last_output;
                        for (int i = embd_inp.size() - 16; i < (int) embd_inp.size(); i++) {
                            last_output += llama_token_to_piece(ctx_llama, embd_inp[i]);
                        }
                        last_output += llama_token_to_piece(ctx_llama, embd[0]);

                        for (std::string & antiprompt : antiprompts) {
                            if (last_output.find(antiprompt.c_str(), last_output.length() - antiprompt.length(), antiprompt.length()) != std::string::npos) {
                                done = true;
                                text_to_speak = ::replace(text_to_speak, antiprompt, "");
                                fflush(stdout);
                                need_to_save_session = true;
                                break;
                            }
                        }
                    }

                    is_running = sdl_poll_events();

                    if (!is_running) {
                        break;
                    }
                }

                //speak_with_file(params.speak, text_to_speak, params.speak_file, voice_id);
                if (text_to_speak.size())
				{
					// printf("Got to last text to speak with size %d\n", text_to_speak.size());
	
					// text_to_speak_arr[thread_i] = text_to_speak;
					// reply_part_arr[thread_i] = reply_part;
					// reply_part++;
					// try
					// {
					// 	threads.emplace_back([&] // creates and starts a thread
							// {
							// if (text_to_speak_arr[thread_i-1].size())
							// {
								// send_tts_async(text_to_speak_arr[thread_i-1]); //, current_voice, params.language, params.xtts_url, reply_part_arr[thread_i-1]);
								send_tts_async(text_to_speak); //, current_voice, params.language, params.xtts_url, reply_part_arr[thread_i-1]);
								// text_to_speak_arr[thread_i-1] = "";
								// reply_part_arr[thread_i-1] = 0;
							// } 
							// });
						// thread_i++;
						text_to_speak = "";
					// }
					// catch (const std::exception &ex)
					// {
					// 	std::cerr << "[Exception]: Failed to emplace fin thread: " << ex.what() << '\n';
					// }
				}
				// if ((embd_inp.size() % 10) == 0) printf("\n [t: %zu]\n", embd_inp.size());

				if (llama_interrupted /*&& llama_interrupted_time - llama_start_time < 2.0*/)
				{
					1;
					// printf(" \n[continue speech] (%f)", (llama_interrupted_time - llama_start_time));
				}
				else
				{
					audio.clear();
					// printf("\n [audio cleared fin]\n");
				}

				// llama_end_time = get_current_time_ms();
				// if (params.verbose)
				// {
				// 	llama_time_input = llama_start_generation_time - llama_start_time;
				// 	llama_time_output = llama_end_time - llama_start_generation_time;
				// 	llama_time_total = llama_end_time - llama_start_time;
				// 	printf("\n\n[tokens: %d in + %d out. Input %.3f s + output %.3f s = total: %.3f s]", input_tokens_count, new_tokens, llama_time_input, llama_time_output, llama_time_total);
				// 	printf("\n[Speed: input %.2f t/s + output %.2f t/s = total: %.2f t/s]\n", input_tokens_count / llama_time_input, new_tokens / llama_time_output, new_tokens / llama_time_total);
				// }
				llama_interrupted = 0;
            }
        }
    }

    audio.pause();

    whisper_print_timings(ctx_wsp);
    whisper_free(ctx_wsp);

    // llama_perf_sampler_print(smpl);
    // llama_perf_context_print(ctx_llama);

    // llama_sampler_free(smpl);
    llama_batch_free(batch);
    llama_free(ctx_llama);

	llama_backend_free();

    return 0;
}
