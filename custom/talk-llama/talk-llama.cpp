// =============================================================================
// talk-llama-custom
// Voice assistant combining Whisper STT, llama-server LLM, and Piper TTS
// with Wyoming protocol integration and LLM-bypass custom commands.
//
// Based on whisper.cpp/examples/talk-llama by Georgi Gerganov
//   https://github.com/ggerganov/whisper.cpp
//
// Original talk-llama-fast modifications by Mozer
//   https://github.com/Mozer/talk-llama-fast
//
// Further modifications by Paul Mobbs (2024-2026)
//   https://github.com/pmamd/voice-assistant-custom-commands
//
// llama-server HTTP backend:
//   Replaces embedded llama.cpp with HTTP calls to llama-server's
//   /completion endpoint. This enables GPU-accelerated inference on
//   a separate process or remote machine over ethernet.
//
// Credits:
//   Whisper STT        - OpenAI
//   whisper.cpp        - Georgi Gerganov and contributors (MIT License)
//   LLaMA / llama.cpp  - Meta AI / Georgi Gerganov (MIT License)
//   Mistral models     - Mistral AI
//   Piper TTS          - Rhasspy project
//   Wyoming Protocol   - Rhasspy project
//
// License:
//   Custom code (this file and custom/):  see repository LICENSE
//   whisper.cpp:  MIT License - see whisper.cpp/LICENSE
//   LLaMA models: Meta AI license - see individual model terms
// =============================================================================

#include "common-sdl.h"
#include "common.h"
#include "console.h"
#include "console.cpp"
#include "whisper.h"
#include "json.hpp"

#include <cassert>
#include <cstdio>
#include <fstream>
#include <regex>
#include <string>
#include <thread>
#include <vector>
#include <sstream>
#include <atomic>

#include <iostream>

#include <algorithm>
#include <cctype>
#include <locale>
#include <codecvt>
#include <queue>

#include <fstream>

#include <clocale>
#include <curl/curl.h>
#include <unordered_set>
#include <ctype.h>
#include <map>
#include <iterator>
#include <ctime>

// For TTS communication
#include "tts-socket.h"
#include "tts-request.h"

// For tool calling system
#include "tool-system.h"
#include "tool-parser.h"
#include "wyoming-client.h"

// Signal handling for graceful shutdown
// Global flag set by the SIGINT/SIGTERM signal handler to request a graceful shutdown.
volatile sig_atomic_t g_sigint_received = 0;

// Signal handler for SIGINT/SIGTERM.
// First signal sets g_sigint_received for a graceful exit; second signal force-exits.
void sigint_handler(int sig) {
	static int sigint_count = 0;
	sigint_count++;
	if (sigint_count == 1) {
		fprintf(stderr, "\n\nCaught signal %d (Ctrl+C), shutting down gracefully...\n", sig);
		fprintf(stderr, "Press Ctrl+C again to force quit.\n");
		g_sigint_received = 1;
	} else {
		fprintf(stderr, "\n\nForce quit! Exiting immediately...\n");
		_exit(1);
	}
}

// global
// Stores the name of the most recently pressed hotkey (e.g. "Ctrl+Space", "Escape").
// Read by the main loop; written by the hotkey background thread.
std::string g_hotkey_pressed = "";

// command-line parameters
// All runtime configuration parameters parsed from command-line arguments.
// Covers Whisper STT settings, LLM sampling parameters, TTS config, VAD thresholds,
// model paths, instruct presets, and test/debug flags.
struct whisper_params
{
	int32_t n_threads = std::min(4, (int32_t)std::thread::hardware_concurrency());
	int32_t voice_ms = 10000;
	int32_t capture_id = -1;
	int32_t max_tokens = 32;
	int32_t audio_ctx = 0;

	float vad_thold = 0.6f;
	float vad_start_thold = 0.000270f; // 0 to turn off, you can see your current energy_last (loudness level) when running with --print-energy param
	int vad_last_ms = 700;  // Reduced from 1250ms to 700ms for faster stop response
	float freq_thold = 100.0f;
	float min_energy = 0.0012f; // Minimum energy threshold to prevent TTS feedback

	bool speed_up = false;
	bool translate = false;
	bool print_special = false;
	bool print_energy = false;
	bool debug = false;
	bool no_timestamps = true;
	bool verbose_prompt = false;
	bool verbose = false;
	bool use_gpu = true;
	bool allow_newline = false;
	bool multi_chars = false;
	bool xtts_intro = false;
	bool seqrep = false;
	bool push_to_talk = false;
	int split_after = 0;
	int sleep_before_xtts = 0; // in ms

	std::string person = "Georgi";
	std::string bot_name = "LLaMA";
	std::string xtts_voice = "emma_1";
	std::string wake_cmd = "";
	std::string heard_ok = "";
	std::string language = "en";
	std::string model_wsp = "models/ggml-base.en.bin";
	std::string speak = "./examples/talk-llama/speak";
	std::string xtts_control_path = "";
	std::string xtts_url = "http://0.0.0.0:10200"; // modified for wyoming piper
	std::string google_url = "http://localhost:8003/";
	std::string prompt = "";
	std::string instruct_preset = "";
	std::map<std::string, std::string> instruct_preset_data = {
		{"system_prompt_prefix", ""},
		{"system_prompt_suffix", ""},
		{"user_message_prefix", ""},
		{"user_message_suffix", ""},
		{"bot_message_prefix", ""},
		{"bot_message_suffix", ""},
		{"stop_sequence", ""}};
	std::string fname_out;
	std::string stop_words = "";
	std::string test_input_file = ""; // path to test audio input file (for automated testing)
	int32_t n_predict = 300;
	int32_t min_tokens = 0;
	float temp = 0.5;
	float repeat_penalty = 1.10;

	// llama-server HTTP backend
	std::string llama_url = "http://localhost:8080";
};

// Prints the full help/usage message listing every CLI option and its default value.
void whisper_print_usage(int argc, const char **argv, const whisper_params &params);

// Parses command-line arguments into a whisper_params struct.
// Returns false and prints usage if an unknown argument is encountered.
bool whisper_params_parse(int argc, const char **argv, whisper_params &params)
{
	for (int i = 1; i < argc; i++)
	{
		std::string arg = argv[i];

		if (arg == "-h" || arg == "--help")
		{
			whisper_print_usage(argc, argv, params);
			exit(0);
		}
		else if (arg == "-t" || arg == "--threads")
		{
			params.n_threads = std::stoi(argv[++i]);
		}
		else if (arg == "-vms" || arg == "--voice-ms")
		{
			params.voice_ms = std::stoi(argv[++i]);
		}
		else if (arg == "-c" || arg == "--capture")
		{
			params.capture_id = std::stoi(argv[++i]);
		}
		else if (arg == "-mt" || arg == "--max-tokens")
		{
			params.max_tokens = std::stoi(argv[++i]);
		}
		else if (arg == "-ac" || arg == "--audio-ctx")
		{
			params.audio_ctx = std::stoi(argv[++i]);
		}
		else if (arg == "-vth" || arg == "--vad-thold")
		{
			params.vad_thold = std::stof(argv[++i]);
		}
		else if (arg == "-vths" || arg == "--vad-start-thold")
		{
			params.vad_start_thold = std::stof(argv[++i]);
		}
		else if (arg == "-vlm" || arg == "--vad-last-ms")
		{
			params.vad_last_ms = std::stoi(argv[++i]);
		}
		else if (arg == "-fth" || arg == "--freq-thold")
		{
			params.freq_thold = std::stof(argv[++i]);
		}
		else if (arg == "-me" || arg == "--min-energy")
		{
			params.min_energy = std::stof(argv[++i]);
		}
		else if (arg == "-su" || arg == "--speed-up")
		{
			params.speed_up = true;
		}
		else if (arg == "-tr" || arg == "--translate")
		{
			params.translate = true;
		}
		else if (arg == "-ps" || arg == "--print-special")
		{
			params.print_special = true;
		}
		else if (arg == "-pe" || arg == "--print-energy")
		{
			params.print_energy = true;
		}
		else if (arg == "--debug")
		{
			params.debug = true;
		}
		else if (arg == "-vp" || arg == "--verbose-prompt")
		{
			params.verbose_prompt = true;
		}
		else if (arg == "--verbose")
		{
			params.verbose = true;
		}
		else if (arg == "-ng" || arg == "--no-gpu")
		{
			params.use_gpu = false;
		}
		else if (arg == "-p" || arg == "--person")
		{
			params.person = argv[++i];
		}
		else if (arg == "-bn" || arg == "--bot-name")
		{
			params.bot_name = argv[++i];
		}
		else if (arg == "-w" || arg == "--wake-command")
		{
			params.wake_cmd = argv[++i];
		}
		else if (arg == "-ho" || arg == "--heard-ok")
		{
			params.heard_ok = argv[++i];
		}
		else if (arg == "-l" || arg == "--language")
		{
			params.language = argv[++i];
		}
		else if (arg == "-mw" || arg == "--model-whisper")
		{
			params.model_wsp = argv[++i];
		}
		else if (arg == "-s" || arg == "--speak")
		{
			params.speak = argv[++i];
		}
		else if (arg == "-n" || arg == "--n_predict")
		{
			params.n_predict = std::stoi(argv[++i]);
		}
		else if (arg == "--temp")
		{
			params.temp = std::stof(argv[++i]);
		}
		else if (arg == "--repeat_penalty")
		{
			params.repeat_penalty = std::stof(argv[++i]);
		}
		else if (arg == "--xtts-voice")
		{
			params.xtts_voice = argv[++i];
		}
		else if (arg == "--xtts-url")
		{
			params.xtts_url = argv[++i];
		}
		else if (arg == "--google-url")
		{
			params.google_url = argv[++i];
		}
		else if (arg == "--allow-newline")
		{
			params.allow_newline = true;
		}
		else if (arg == "--multi-chars")
		{
			params.multi_chars = true;
		}
		else if (arg == "--xtts-intro")
		{
			params.xtts_intro = true;
		}
		else if (arg == "--sleep-before-xtts")
		{
			params.sleep_before_xtts = std::stoi(argv[++i]);
		}
		else if (arg == "--seqrep")
		{
			params.seqrep = true;
		}
		else if (arg == "--push-to-talk")
		{
			params.push_to_talk = true;
		}
		else if (arg == "--split-after")
		{
			params.split_after = std::stoi(argv[++i]);
		}
		else if (arg == "--min-tokens")
		{
			params.min_tokens = std::stoi(argv[++i]);
		}
		else if (arg == "--stop-words")
		{
			params.stop_words = argv[++i];
		}
		else if (arg == "--instruct-preset")
		{
			params.instruct_preset = argv[++i];
		}
		else if (arg == "--prompt-file")
		{
			std::ifstream file(argv[++i]);
			std::copy(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>(), back_inserter(params.prompt));
			if (params.prompt.back() == '\n')
			{
				params.prompt.pop_back();
			}
		}
		else if (arg == "-f" || arg == "--file")
		{
			params.fname_out = argv[++i];
		}
		else if (arg == "--test-input")
		{
			params.test_input_file = argv[++i];
		}
		else if (arg == "--llama-url")
		{
			params.llama_url = argv[++i];
		}
		else
		{
			fprintf(stderr, "error: unknown argument: %s\n", arg.c_str());
			whisper_print_usage(argc, argv, params);
			exit(0);
		}
	}

	return true;
}

void whisper_print_usage(int /*argc*/, const char **argv, const whisper_params &params)
{
	fprintf(stderr, "\n");
	fprintf(stderr, "usage: %s [options]\n", argv[0]);
	fprintf(stderr, "\n");
	fprintf(stderr, "options:\n");
	fprintf(stderr, "  -h,       --help           [default] show this help message and exit\n");
	fprintf(stderr, "  -t N,     --threads N      [%-7d] number of threads to use during computation\n", params.n_threads);
	fprintf(stderr, "  -vms N,   --voice-ms N     [%-7d] voice duration in milliseconds\n", params.voice_ms);
	fprintf(stderr, "  -c ID,    --capture ID     [%-7d] capture device ID\n", params.capture_id);
	fprintf(stderr, "  -mt N,    --max-tokens N   [%-7d] maximum number of tokens per audio chunk\n", params.max_tokens);
	fprintf(stderr, "  -ac N,    --audio-ctx N    [%-7d] audio context size (0 - all)\n", params.audio_ctx);
	fprintf(stderr, "  -vth N,   --vad-thold N    [%-7.2f] voice avg activity detection threshold\n", params.vad_thold);
	fprintf(stderr, "  -vths N,  --vad-start-thold N [%-7.6f] vad min level to stop tts, 0: off, 0.000270: default\n", params.vad_start_thold);
	fprintf(stderr, "  -vlm N,   --vad-last-ms N  [%-7d] vad min silence after speech, ms\n", params.vad_last_ms);
	fprintf(stderr, "  -fth N,   --freq-thold N   [%-7.2f] high-pass frequency cutoff\n", params.freq_thold);
	fprintf(stderr, "  -me N,    --min-energy N   [%-7.4f] minimum energy threshold (prevents TTS feedback)\n", params.min_energy);
	fprintf(stderr, "  -su,      --speed-up       [%-7s] speed up audio by x2 (not working)\n", params.speed_up ? "true" : "false");
	fprintf(stderr, "  -tr,      --translate      [%-7s] translate from source language to english\n", params.translate ? "true" : "false");
	fprintf(stderr, "  -ps,      --print-special  [%-7s] print special tokens\n", params.print_special ? "true" : "false");
	fprintf(stderr, "  -pe,      --print-energy   [%-7s] print sound energy (for debugging)\n", params.print_energy ? "true" : "false");
	fprintf(stderr, "  --debug                    [%-7s] print debug info\n", params.debug ? "true" : "false");
	fprintf(stderr, "  -vp,      --verbose-prompt [%-7s] print prompt at start\n", params.verbose_prompt ? "true" : "false");
	fprintf(stderr, "  --verbose                  [%-7s] print speed\n", params.verbose ? "true" : "false");
	fprintf(stderr, "  -ng,      --no-gpu         [%-7s] disable GPU (whisper only)\n", params.use_gpu ? "false" : "true");
	fprintf(stderr, "  -p NAME,  --person NAME    [%-7s] person name (for prompt selection)\n", params.person.c_str());
	fprintf(stderr, "  -bn NAME, --bot-name NAME  [%-7s] bot name (to display)\n", params.bot_name.c_str());
	fprintf(stderr, "  -w TEXT,  --wake-command T [%-7s] wake-up command to listen for\n", params.wake_cmd.c_str());
	fprintf(stderr, "  -ho TEXT, --heard-ok TEXT  [%-7s] said by TTS before generating reply\n", params.heard_ok.c_str());
	fprintf(stderr, "  -l LANG,  --language LANG  [%-7s] spoken language\n", params.language.c_str());
	fprintf(stderr, "  -mw FILE, --model-whisper  [%-7s] whisper model file\n", params.model_wsp.c_str());
	fprintf(stderr, "  -s FILE,  --speak TEXT     [%-7s] command for TTS\n", params.speak.c_str());
	fprintf(stderr, "  --prompt-file FNAME        [%-7s] file with custom prompt to start dialog\n", "");
	fprintf(stderr, "  --instruct-preset TEXT     [%-7s] instruct preset to use without .json \n", "");
	fprintf(stderr, "  -f FNAME, --file FNAME     [%-7s] text output file name\n", params.fname_out.c_str());
	fprintf(stderr, "  -n N,     --n_predict N    [%-7d] Max number of tokens to predict\n", params.n_predict);
	fprintf(stderr, "  --temp N                   [%-7.2f] Temperature \n", params.temp);
	fprintf(stderr, "  --repeat_penalty N         [%-7.2f] repeat_penalty \n", params.repeat_penalty);
	fprintf(stderr, "  --xtts-voice NAME          [%-7s] xtts voice without .wav\n", params.xtts_voice.c_str());
	fprintf(stderr, "  --xtts-url TEXT            [%-7s] xtts/silero server URL, with trailing slash\n", params.xtts_url.c_str());
	fprintf(stderr, "  --xtts-intro               [%-7s] xtts instant short random intro like Hmmm.\n", params.xtts_intro ? "true" : "false");
	fprintf(stderr, "  --sleep-before-xtts        [%-7d] sleep llama inference before xtts, ms.\n", params.sleep_before_xtts);
	fprintf(stderr, "  --google-url TEXT          [%-7s] langchain google-serper server URL, with /\n", params.google_url.c_str());
	fprintf(stderr, "  --allow-newline            [%-7s] allow new line in llama output\n", params.allow_newline ? "true" : "false");
	fprintf(stderr, "  --multi-chars              [%-7s] xtts will use same wav name as in llama output\n", params.multi_chars ? "true" : "false");
	fprintf(stderr, "  --push-to-talk             [%-7s] hold Alt to speak\n", params.push_to_talk ? "true" : "false");
	fprintf(stderr, "  --seqrep                   [%-7s] sequence repetition penalty\n", params.seqrep ? "true" : "false");
	fprintf(stderr, "  --split-after N            [%-7d] split after first n tokens for tts\n", params.split_after);
	fprintf(stderr, "  --min-tokens N             [%-7d] min new tokens to output\n", params.min_tokens);
	fprintf(stderr, "  --stop-words TEXT          [%-7s] llama stop w: separated by ; \n", params.stop_words.c_str());
	fprintf(stderr, "  --llama-url TEXT           [%-7s] llama-server URL\n", params.llama_url.c_str());
	fprintf(stderr, "\n");
}

// returns seconds since epoch with microsecond precision. e.g. 15244.575123 (15244 s and 575.123 ms)
// Returns the current wall-clock time in seconds (with microsecond precision).
double get_current_time_ms()
{
	auto now = std::chrono::high_resolution_clock::now();

	// Convert to microseconds since the Unix epoch for higher precision
	auto duration = now.time_since_epoch();
	double micros = (double)std::chrono::duration_cast<std::chrono::microseconds>(duration).count() / 1000000.0;

	return micros;
}

// Runs Whisper speech-to-text on a PCM float audio buffer.
// Returns the transcribed text; sets prob0 to the average token probability
// and t_ms to the inference time in milliseconds.
std::string transcribe(
	whisper_context *ctx,
	const whisper_params &params,
	const std::vector<float> &pcmf32,
	const std::string prompt_text,
	float &prob,
	int64_t &t_ms)
{
	const auto t_start = std::chrono::high_resolution_clock::now();

	if (params.debug) {
		printf("%.3f in transcribe\n", get_current_time_ms());
	}
	prob = 0.0f;
	t_ms = 0;

	std::vector<whisper_token> prompt_tokens;

	whisper_full_params wparams = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);

	prompt_tokens.resize(1024);
	prompt_tokens.resize(whisper_tokenize(ctx, prompt_text.c_str(), prompt_tokens.data(), prompt_tokens.size()));

	wparams.print_progress = false;
	wparams.print_special = params.print_special;
	wparams.print_realtime = false;
	wparams.print_timestamps = !params.no_timestamps;
	wparams.translate = params.translate;
	wparams.no_context = true;
	wparams.single_segment = true;
	wparams.max_tokens = params.max_tokens;
	wparams.language = params.language.c_str();
	wparams.n_threads = params.n_threads;

	wparams.prompt_tokens = prompt_tokens.empty() ? nullptr : prompt_tokens.data();
	wparams.prompt_n_tokens = prompt_tokens.empty() ? 0 : prompt_tokens.size();

	wparams.audio_ctx = params.audio_ctx;
	wparams.no_timestamps = true;

	if (whisper_full(ctx, wparams, pcmf32.data(), pcmf32.size()) != 0)
	{
		return "";
	}

	int prob_n = 0;
	std::string result;

	const int n_segments = whisper_full_n_segments(ctx);
	for (int i = 0; i < n_segments; ++i)
	{
		const char *text = whisper_full_get_segment_text(ctx, i);

		result += text;

		const int n_tokens = whisper_full_n_tokens(ctx, i);
		for (int j = 0; j < n_tokens; ++j)
		{
			const auto token = whisper_full_get_token_data(ctx, i, j);

			prob += token.p;
			++prob_n;
		}
	}
	if (params.debug) {
		printf("%.3f after n_segments\n", get_current_time_ms());
	}

	if (prob_n > 0)
	{
		prob /= prob_n;
	}

	const auto t_end = std::chrono::high_resolution_clock::now();
	t_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t_end - t_start).count();

	return result;
}

// Splits a string into a vector of whitespace-delimited words.
std::vector<std::string> get_words(const std::string &txt)
{
	std::vector<std::string> words;

	std::istringstream iss(txt);
	std::string word;
	while (iss >> word)
	{
		words.push_back(word);
	}

	return words;
}

// trim from start (in place)
// Removes leading whitespace from a string in place.
inline void ltrim(std::string &s)
{
	s.erase(s.begin(), std::find_if(s.begin(), s.end(), [](unsigned char ch)
									{ return !std::isspace(ch); }));
}

// trim from end (in place)
// Removes trailing whitespace from a string in place.
inline void rtrim(std::string &s)
{
	s.erase(std::find_if(s.rbegin(), s.rend(), [](unsigned char ch)
						 { return !std::isspace(ch); })
				.base(),
			s.end());
}

// trim from both ends (in place)
// Removes leading and trailing whitespace from a string in place.
inline void trim(std::string &s)
{
	rtrim(s);
	ltrim(s);
}

// Returns a lowercased copy of the string using the current locale.
// Note: does not handle non-Latin UTF-8 characters correctly.
std::string LowerCase(const std::string &text)
{
	std::string lowerCasedText;
	for (const auto &c : text)
	{
		lowerCasedText += std::tolower(c, std::locale());
	}
	return lowerCasedText;
}

// libcurl write callback: appends received HTTP response data to a std::string buffer.
static size_t WriteCallback(char *ptr, size_t size, size_t nmemb, void *userdata)
{
	((std::string *)userdata)->append((const char *)ptr, size * nmemb);
	return size * nmemb;
}

// Removes all trailing occurrences of a specific character from a string.
std::string RemoveTrailingCharacters(const std::string &inputString, const char targetCharacter)
{
	auto lastNonTargetPosition = std::find_if(inputString.rbegin(), inputString.rend(), [targetCharacter](auto ch)
											  { return ch != targetCharacter; });
	return std::string(inputString.begin(), lastNonTargetPosition.base());
}

// Removes trailing occurrences of any character in a UTF-32 set from a UTF-8 string.
std::string RemoveTrailingCharactersUtf8(const std::string &inputString, const std::u32string &targetCharacter)
{
	std::wstring_convert<std::codecvt_utf8<char32_t>, char32_t> converter;
	std::u32string u32_input = converter.from_bytes(inputString);

	auto lastNonTargetPosition = std::find_if(u32_input.rbegin(), u32_input.rend(), [&targetCharacter](char32_t ch)
											  { return targetCharacter.find(ch) == std::u32string::npos; });

	std::string result = converter.to_bytes(std::u32string(u32_input.begin(), lastNonTargetPosition.base()));
	return result;
}

// URL-encodes a string using libcurl's curl_easy_escape.
std::string UrlEncode(const std::string &str)
{
	CURL *curl = curl_easy_init();
	if (curl)
	{
		char *encodedUrl = curl_easy_escape(curl, str.c_str(), str.length());
		std::string escapedUrl(encodedUrl);
		curl_free(encodedUrl);
		curl_easy_cleanup(curl);
		return escapedUrl;
	}
	return {};
}

// Sends an HTTP POST request with a JSON body built from a key-value map.
// Returns the response body as a string.
std::string send_curl_json(const std::string &url, const std::map<std::string, std::string> &params)
{
	CURL *curl;
	CURLcode res;
	std::string readBuffer;

	/* Initialize curl */
	curl = curl_easy_init();
	if (!curl)
	{
		throw std::runtime_error("Failed to initialize curl");
	}

	try
	{
		curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
		curl_easy_setopt(curl, CURLOPT_VERBOSE, 0L);

		/* Convert map to query string */
		std::ostringstream oss;
		bool firstParam = true;
		oss << "{";
		for (auto param : params)
		{
			if (!firstParam)
				oss << ',';
			oss << "\"" << param.first << "\":\"" << param.second << "\"";
			firstParam = false;
		};
		oss << "}";
		fprintf(stdout, "send_curl_json: %s\n", oss.str().c_str());
		curl_easy_setopt(curl, CURLOPT_HTTPHEADER, curl_slist_append(nullptr, "Content-Type:application/json"));
		curl_easy_setopt(curl, CURLOPT_POSTFIELDS, oss.str().c_str());
		curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
		curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);
		res = curl_easy_perform(curl);

		if (res != CURLE_OK)
		{
			throw std::runtime_error(std::string("cURL error: ") + curl_easy_strerror(res));
		}
		else
		{
			}
	}
	catch (...)
	{ // exception handler
	}
	curl_easy_cleanup(curl);

	return readBuffer;
}

// Sends a simple HTTP GET request to the given URL.
// Returns the response body as a string.
std::string send_curl(std::string url)
{
	CURL *curl;
	CURLcode res;
	std::string readBuffer;

	curl = curl_easy_init();
	if (curl)
	{
		curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
		curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
		curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);
		res = curl_easy_perform(curl);
		curl_easy_cleanup(curl);
	}

	return readBuffer;
}

// Returns the number of Unicode code points (characters) in a UTF-8 string.
int utf8_length(const std::string &str)
{
	int c, i, ix, q;
	for (q = 0, i = 0, ix = str.length(); i < ix; i++, q++)
	{
		c = (unsigned char)str[i];
		if (c >= 0 && c <= 127)
			i += 0;
		else if ((c & 0xE0) == 0xC0)
			i += 1;
		else if ((c & 0xF0) == 0xE0)
			i += 2;
		else if ((c & 0xF8) == 0xF0)
			i += 3;
		else
			return 0; // invalid utf8
	}
	return q;
}

// Returns a substring using Unicode code-point indices rather than byte indices,
// correctly handling multi-byte UTF-8 characters.
std::string utf8_substr(const std::string &str, unsigned int start, unsigned int leng)
{
	if (leng == 0)
	{
		return "";
	}
	unsigned int c, i, ix, q, min = std::string::npos, max = std::string::npos;
	for (q = 0, i = 0, ix = str.length(); i < ix; i++, q++)
	{
		if (q == start)
		{
			min = i;
		}
		if (q <= start + leng || leng == std::string::npos)
		{
			max = i;
		}

		c = (unsigned char)str[i];
		if (
			c <= 127)
			i += 0;
		else if ((c & 0xE0) == 0xC0)
			i += 1;
		else if ((c & 0xF0) == 0xE0)
			i += 2;
		else if ((c & 0xF8) == 0xF0)
			i += 3;
		else
			return ""; // invalid utf8
	}
	if (q <= start + leng || leng == std::string::npos)
	{
		max = i;
	}
	if (min == std::string::npos || max == std::string::npos)
	{
		return "";
	}
	return str.substr(min, max);
}

// returns name or ""
// Searches for a character name pattern (\nName: ) in the given string.
// Returns the name if found, used for multi-character voice switching in TTS.
std::string find_name(const std::string &str)
{
	if (str.size() >= 4)
	{
		// Search for '\n' character
		size_t pos = str.find("\n");
		if (pos != std::string::npos && pos + 4 <= str.length())
		{
			// If found, search for ':' after '\n'
			size_t endPos = str.find(": ", pos);
			if (endPos == std::string::npos || endPos >= str.length())
			{
				return "";
			}

			// Get the subtring before ' :'
			std::string substr = str.substr(pos + 1, endPos - pos - 1);
			// Remove leading and trailing spaces
			while (*substr.begin() == ' ')
			{
				substr.erase(substr.begin());
			}
			while (*substr.rbegin() == ' ')
			{
				substr.pop_back();
			}
			// Return trimmed substring if its length is less than or equal to 20 characters
			if (substr.length() < 2 || substr.length() > 20)
			{
				return "";
			}
			else
			{
				return substr;
			}
		}
	}
	return "";
}

// Cleans and normalises text (strips parenthetical/HTML/bracket content,
// normalises punctuation), then sends it to the Wyoming-Piper TTS server
// via a raw TCP socket connection. Called from worker threads during generation.
void send_tts_async(std::string text, std::string speaker_wav = "emma_1", std::string language = "en", std::string tts_url = "http://localhost:8020/", int reply_part = 0, bool debug = false)
{
int hSocket, read_size;
    struct sockaddr_in server; // for tts-socket

	if (debug) {
		std::cout << "send_tts_async: " << text;
	}

	// remove (text) and <tag> using regex
	if (text[0] == '(' && text[text.size() - 1] != ')')
		text = +")"; // missing )
	else if (text[0] != '(' && text[text.size() - 1] == ')')
		text = "(" + text;						 // missing (
	std::regex paren_regex(R"(\([^()]*\))");	 // (text)
	std::regex html_regex(R"(<(.*?)>)");		 // // <tag>
	std::regex bracket_regex(R"(\[[^\[\]]*\])"); // [text]
	text = std::regex_replace(text, paren_regex, "");
	text = std::regex_replace(text, html_regex, "");
	text = std::regex_replace(text, bracket_regex, "");

	trim(text);
	text = ::replace(text, "...", ".");
	text = ::replace(text, "..", ".");
	text = ::replace(text, "...", ".");
	text = ::replace(text, "??", "?");
	text = ::replace(text, "!!!", "!");
	text = ::replace(text, "!!", "!");
	text = ::replace(text, "?!", "?");
	text = ::replace(text, "\"", "");
	text = ::replace(text, ")", "");
	text = ::replace(text, "(", "");
	text = ::replace(text, " ?", "?");
	text = ::replace(text, " !", "!");
	text = ::replace(text, " .", ".");
	text = ::replace(text, " ,", ",");

	if (text == "!" || text == "?" || text == ".")
		text = "";
	else if (text == speaker_wav + ": ")
		text = "";
	else if (text == speaker_wav + ":")
		text = "";
	else if (text[text.size() - 1] == ':')
		text[text.size() - 1] = ' ';
	else if (text[text.size() - 1] == '-')
		text[text.size() - 1] = ' ';
	else if (text[text.size() - 1] == '(')
		text[text.size() - 1] = ' ';
	else if (text[text.size() - 1] == ',')
		text[text.size() - 1] = ' ';
	else if (text[text.size() - 1] == '.')
		text[text.size() - 1] = ' ';
	speaker_wav = ::replace(speaker_wav, ":", "");
	speaker_wav = ::replace(speaker_wav, "\n", "");
	speaker_wav = ::replace(speaker_wav, "\r", "");
	speaker_wav = ::replace(speaker_wav, "\"", "");
	trim(speaker_wav);
	if (speaker_wav.size() < 2)
		speaker_wav = "emma_1";
	trim(text);

	if (text[0] == '!' || text[0] == '?' || text[0] == '.' || text[0] == ',' && text.size() >= 2)
		text = utf8_substr(text, 1, utf8_length(text));
	if (text[text.size() - 1] == ',' && text.size() >= 2)
		text = utf8_substr(text, 0, utf8_length(text) - 1);
	trim(text);

	if (text.back() == ':' && text.length() < 15 && text.find(' ') == std::string::npos)
		text = "";
	if (text.size() >= 1 && text != "." && text != "," && text != "!" && text != "\n")
	{
		trim(text);
		text = ::replace(text, "\r", "");
		text = ::replace(text, "\n", " ");
		text = ::replace(text, "\"", "");
		text = ::replace(text, "..", ".");

		int still_running = 1;
		char *json = TTS_RequestEncode(text.c_str());

		//Create socket
		hSocket = TTS_SocketCreate();
		if(hSocket == -1)
		{
			printf("Could not create socket\n");
			return;
		}
		if (debug) {
			printf("Socket is created\n");
		}
		//Connect to remote server
		if (TTS_SocketConnect(hSocket) < 0)
		{
			perror("connect failed.\n");
			return;
		}
		if (debug) {
			printf("Sucessfully conected with server\n");
			printf("Sending request to server:\n");
			printf("%s\n", json);
		}
		//Send data to the server
		TTS_SocketSend(hSocket, json, strlen(json));
		free(json);
		//Received the data from the server
		close(hSocket);
		shutdown(hSocket,0);
		shutdown(hSocket,1);
		shutdown(hSocket,2);
	}
}

// Queue for keyboard input lines typed by the user.
// Written by input_thread_func(), read by the main loop.
std::queue<std::string> input_queue; // global
bool keyboard_input_running = true; // global, not used yet

// Background thread that reads lines from stdin and pushes them onto input_queue.
// Allows the user to type commands in addition to speaking them.
void input_thread_func()
{
	std::string line;
	std::string buffer;
	bool found_another_line = true;

	while (keyboard_input_running)
	{
		do
		{
			found_another_line = console::readline(line, false);
			buffer += line;
		} while (found_another_line);
		trim(buffer); // keyboard input
		// if you paste multiple passages from clipboard, make sure to hit Enter after pasting
		// otherwise last passage won't be pasted (bug). Alternatively you can manually add \n after last passage in copied text

		input_queue.push(buffer);
		buffer = "";
	}
}

// Default Whisper transcription prompt templates.
// Primes Whisper to expect conversational speech directed at a named person.
const std::string k_prompt_whisper = R"(A conversation with a person called {1}.)";
const std::string k_prompt_whisper_ru = R"({1}, Alisa.)";

// Default LLaMA system prompt.
// Placeholders: {0}=person name, {1}=bot name, {2}=time, {3}=year, {4}=chat_symb, {5}=date.
const std::string k_prompt_llama = R"(Text transcript of a never ending dialog, where {0} interacts with an AI assistant named {1}.
{1} is helpful, kind, honest, friendly, good at writing and never fails to answer {0}'s requests immediately and with details and precision.
There are no annotations like (30 seconds passed...) or (to himself), just what {0} and {1} say aloud to each other.
The transcript only includes text, it does not include markup like HTML and Markdown.
{1} responds with short and concise answers.

{0}{4} Hello, {1}!
{1}{4} Hello {0}! How may I help you today?
{0}{4} What time is it?
{1}{4} It is {2} o'clock, {5}, year {3}.
{0}{4} What is a cat?
{1}{4} A cat is a domestic species of small carnivorous mammal. It is the only domesticated species in the family Felidae.
{0}{4} Name a color.
{1}{4} Blue
{0}{4})";

// =============================================================================
// llama-server HTTP streaming client
// =============================================================================

// Data passed to the CURL streaming write callback.
// Accumulates SSE data, parses tokens, dispatches to TTS sentence-by-sentence.
struct llama_stream_context {
	std::atomic<bool>* stop_flag;  // pointer to g_stop_generation
	std::string sse_buffer;        // partial SSE line buffer
	std::string full_response;     // complete generated text
	std::string text_to_speak;     // current sentence accumulator for TTS
	int new_tokens;                // token counter
	bool debug;

	// TTS dispatch state
	const whisper_params* params;
	std::string current_voice;
	std::vector<std::thread>* threads;
	std::string* text_to_speak_arr;
	int* reply_part_arr;
	int* thread_i;
	int* reply_part;

	// Tool call parser
	tool_system::ToolCallParser* tool_parser;
	tool_system::ToolRegistry* tool_registry;

	// Antiprompts for stop detection
	std::vector<std::string>* antiprompts;
	bool done;               // set when an antiprompt is detected

	// Sequence repetition detection
	std::string last_output_buffer;
	std::string last_output_needle;
};

// Dispatch a completed sentence to TTS in a background thread.
static void dispatch_tts_sentence(llama_stream_context* ctx, const std::string& sentence) {
	if (sentence.empty()) return;

	std::string text = sentence;
	text = ::replace(text, "\"", "'");
	if (ctx->antiprompts) {
		for (const auto& ap : *ctx->antiprompts) {
			text = ::replace(text, ap, "");
		}
	}
	trim(text);
	if (text.empty()) return;

	int idx = *ctx->thread_i;
	ctx->text_to_speak_arr[idx] = text;
	ctx->reply_part_arr[idx] = *ctx->reply_part;
	(*ctx->reply_part)++;

	try {
		int current_thread_idx = idx;
		auto params = ctx->params;
		auto current_voice = ctx->current_voice;
		ctx->threads->emplace_back([params, current_thread_idx, current_voice,
		                            text_arr = ctx->text_to_speak_arr,
		                            rp_arr = ctx->reply_part_arr]() {
			if (text_arr[current_thread_idx].size()) {
				send_tts_async(text_arr[current_thread_idx], current_voice,
				               params->language, params->xtts_url,
				               rp_arr[current_thread_idx], params->debug);
				text_arr[current_thread_idx] = "";
				rp_arr[current_thread_idx] = 0;
			}
		});
		(*ctx->thread_i)++;
	} catch (const std::exception& ex) {
		std::cerr << "[Exception]: Failed to dispatch TTS thread: " << ex.what() << '\n';
	}
}

// Check if the recent output matches any antiprompt (stop word).
static bool check_antiprompts(const std::string& recent_output, const std::vector<std::string>& antiprompts) {
	for (const auto& ap : antiprompts) {
		if (recent_output.length() >= ap.length()) {
			size_t pos = recent_output.find(ap, recent_output.length() - ap.length());
			if (pos != std::string::npos) {
				return true;
			}
		}
	}
	return false;
}

// CURL write callback for SSE streaming from llama-server /completion endpoint.
// Parses "data: {...}" lines, extracts token content, accumulates sentences,
// dispatches to TTS, and checks stop conditions.
static size_t llama_stream_write_callback(char* ptr, size_t size, size_t nmemb, void* userdata) {
	llama_stream_context* ctx = (llama_stream_context*)userdata;

	if (ctx->stop_flag->load() || ctx->done) {
		return 0; // abort transfer
	}

	size_t total = size * nmemb;
	ctx->sse_buffer.append(ptr, total);

	// Process complete lines
	size_t pos;
	while ((pos = ctx->sse_buffer.find('\n')) != std::string::npos) {
		std::string line = ctx->sse_buffer.substr(0, pos);
		ctx->sse_buffer.erase(0, pos + 1);

		// Remove trailing \r
		if (!line.empty() && line.back() == '\r') {
			line.pop_back();
		}

		// Skip empty lines and non-data lines
		if (line.empty() || line.find("data: ") != 0) {
			continue;
		}

		// Extract JSON after "data: "
		std::string json_str = line.substr(6);

		try {
			auto j = nlohmann::json::parse(json_str);

			// Check for stop
			bool is_stop = false;
			if (j.contains("stop") && j["stop"].is_boolean()) {
				is_stop = j["stop"].get<bool>();
			}

			if (is_stop) {
				// Flush remaining text to TTS
				if (!ctx->text_to_speak.empty()) {
					dispatch_tts_sentence(ctx, ctx->text_to_speak);
					ctx->text_to_speak.clear();
				}
				ctx->done = true;
				break;
			}

			// Extract token content - llama-server uses "content" at top level
			std::string token_text;
			if (j.contains("content") && j["content"].is_string()) {
				token_text = j["content"].get<std::string>();
			}

			if (token_text.empty()) continue;

			ctx->new_tokens++;
			ctx->full_response += token_text;

			// Feed to tool parser if available
			if (ctx->tool_parser) {
				bool tool_detected = ctx->tool_parser->feedToken(token_text);
				if (tool_detected && ctx->tool_parser->hasToolCall()) {
					tool_system::ToolCall call = ctx->tool_parser->getToolCall();
					fprintf(stdout, "\n[Tool Call: %s]\n", call.name.c_str());
					if (ctx->tool_registry) {
						tool_system::ToolResult result = ctx->tool_registry->execute(call.name, call.arguments);
						if (result.success) {
							fprintf(stdout, "[Tool executed: %s]\n", result.message.c_str());
							// Speak the tool result and stop LLM generation
							// (LLM commentary after a tool call is redundant and causes TTS overlap)
							if (!result.message.empty()) {
								dispatch_tts_sentence(ctx, result.message);
							}
							ctx->done = true;
						} else {
							fprintf(stderr, "[Tool execution failed: %s]\n", result.message.c_str());
						}
					}
					ctx->tool_parser->reset();
					continue;
				}

				// Get clean text (excluding tool tags)
				std::string clean_text = ctx->tool_parser->getText();
				std::replace(clean_text.begin(), clean_text.end(), '\n', ' ');
				if (!clean_text.empty()) {
					token_text = clean_text;
				} else {
					continue;
				}
			}

			// Print token
			printf("%s", token_text.c_str());
			fflush(stdout);

			// Accumulate for TTS
			ctx->text_to_speak += token_text;

			// Check antiprompts on recent output
			if (ctx->antiprompts && check_antiprompts(ctx->full_response, *ctx->antiprompts)) {
				// Remove the antiprompt text from text_to_speak
				for (const auto& ap : *ctx->antiprompts) {
					ctx->text_to_speak = ::replace(ctx->text_to_speak, ap, "");
				}
				if (!ctx->text_to_speak.empty()) {
					dispatch_tts_sentence(ctx, ctx->text_to_speak);
					ctx->text_to_speak.clear();
				}
				ctx->done = true;
				break;
			}

			// Sequence repetition detection (simplified string-based version)
			if (ctx->params->seqrep) {
				ctx->last_output_needle += token_text;
				if (utf8_length(ctx->last_output_needle) > 25) {
					ctx->last_output_needle = utf8_substr(ctx->last_output_needle, 5,
						utf8_length(ctx->last_output_needle) - 5);
				}

				char last_char = token_text.back();
				if (last_char == ' ' || last_char == '.' || last_char == ',' ||
				    last_char == '!' || last_char == '?') {
					if (utf8_length(ctx->last_output_buffer) > 300 &&
					    utf8_length(ctx->last_output_needle) >= 20 &&
					    ctx->last_output_buffer.find(ctx->last_output_needle) != std::string::npos) {
						printf(" [LOOP detected - stopping]\n");
						ctx->done = true;
						break;
					}
				}
				if (utf8_length(ctx->last_output_buffer) > 1000) {
					ctx->last_output_buffer = utf8_substr(ctx->last_output_buffer, 100,
						utf8_length(ctx->last_output_buffer) - 100);
				}
				ctx->last_output_buffer += token_text;
			}

			// Check for sentence boundary -> dispatch to TTS
			int text_len = ctx->text_to_speak.size();
			if (text_len >= 2 && ctx->new_tokens >= 2) {
				char last = ctx->text_to_speak[text_len - 1];
				bool is_boundary = (last == '.' || last == '?' || last == '!' ||
				                    last == ';' || last == ':' || last == '\n');

				// Also split on " - " (dash with spaces)
				if (text_len >= 3 && ctx->text_to_speak[text_len - 2] == ' ' && last == '-') {
					is_boundary = true;
				}

				// split_after logic
				if (ctx->params->split_after && ctx->new_tokens == ctx->params->split_after) {
					is_boundary = true;
				}

				if (is_boundary) {
					dispatch_tts_sentence(ctx, ctx->text_to_speak);
					ctx->text_to_speak.clear();

					if (ctx->params->sleep_before_xtts) {
						std::this_thread::sleep_for(
							std::chrono::milliseconds(ctx->params->sleep_before_xtts));
					}
				}
			}
		} catch (const nlohmann::json::exception& e) {
			if (ctx->debug) {
				fprintf(stderr, "[JSON parse error: %s] line: %s\n", e.what(), json_str.c_str());
			}
		}
	}

	return ctx->done ? 0 : total;
}

// Send a prompt to llama-server's /completion endpoint with SSE streaming.
// Returns the full response text. Tokens are dispatched to TTS in real-time
// via the streaming callback.
std::string llama_server_generate(
	const std::string& prompt,
	const std::string& llama_url,
	const whisper_params& params,
	std::atomic<bool>& stop_flag,
	std::vector<std::string>& stop_words,
	llama_stream_context& stream_ctx)
{
	CURL* curl = curl_easy_init();
	if (!curl) {
		fprintf(stderr, "Failed to init CURL for llama-server\n");
		return "";
	}

	// Build JSON request body
	nlohmann::json request_body;
	request_body["prompt"] = prompt;
	request_body["n_predict"] = params.n_predict;
	request_body["temperature"] = params.temp;
	request_body["stream"] = true;
	request_body["repeat_penalty"] = params.repeat_penalty;

	// Build stop array
	nlohmann::json stop_arr = nlohmann::json::array();
	for (const auto& sw : stop_words) {
		stop_arr.push_back(sw);
	}
	request_body["stop"] = stop_arr;

	std::string body = request_body.dump();
	std::string url = llama_url + "/completion";

	if (params.debug) {
		fprintf(stderr, "[llama-server] POST %s\n", url.c_str());
		fprintf(stderr, "[llama-server] Body: %s\n", body.c_str());
	}

	struct curl_slist* headers = nullptr;
	headers = curl_slist_append(headers, "Content-Type: application/json");
	headers = curl_slist_append(headers, "Accept: text/event-stream");

	curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
	curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
	curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
	curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, llama_stream_write_callback);
	curl_easy_setopt(curl, CURLOPT_WRITEDATA, &stream_ctx);
	curl_easy_setopt(curl, CURLOPT_VERBOSE, 0L);
	// No timeout - streaming can take a while
	curl_easy_setopt(curl, CURLOPT_TIMEOUT, 0L);
	curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);

	CURLcode res = curl_easy_perform(curl);

	if (res != CURLE_OK && res != CURLE_WRITE_ERROR) {
		// CURLE_WRITE_ERROR is expected when we abort via returning 0 from callback
		fprintf(stderr, "[llama-server] CURL error: %s\n", curl_easy_strerror(res));
	}

	curl_slist_free_all(headers);
	curl_easy_cleanup(curl);

	return stream_ctx.full_response;
}

// Check if llama-server is reachable by hitting /health endpoint.
bool llama_server_health_check(const std::string& llama_url) {
	CURL* curl = curl_easy_init();
	if (!curl) return false;

	std::string url = llama_url + "/health";
	std::string response;

	curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
	curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
	curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
	curl_easy_setopt(curl, CURLOPT_TIMEOUT, 5L);
	curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);

	CURLcode res = curl_easy_perform(curl);
	long http_code = 0;
	curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
	curl_easy_cleanup(curl);

	if (res == CURLE_OK && http_code == 200) {
		return true;
	}
	return false;
}

// -------------------------------------------------------------------------
// Main application entry point.
// Initialises all subsystems (Whisper, llama-server, Wyoming TTS, tool system, audio),
// then runs the listen -> transcribe -> generate -> speak loop until shutdown.
// -------------------------------------------------------------------------
int run(int argc, const char **argv)
{
	// Set up signal handlers
	signal(SIGINT, sigint_handler);
	signal(SIGTERM, sigint_handler);

	whisper_params params;
	std::vector<std::thread> threads;
	std::thread t;
	int thread_i = 0;
	std::atomic<bool> g_stop_generation{false}; // signal background generation to stop
	std::atomic<bool> g_generation_running{false}; // true while LLM generation thread is live
	std::thread g_llm_thread; // background generation thread
	int reply_part = 0;
	std::string text_to_speak_arr[150];
	int reply_part_arr[150];

#ifdef HOTKEYS
	HWND cur_window_handle = GetForegroundWindow(); // i hope you run a window that has focus
#endif
	if (whisper_params_parse(argc, argv, params) == false)
	{
		return 1;
	}

	if (params.language != "auto" && whisper_lang_id(params.language.c_str()) == -1)
	{
		fprintf(stderr, "error: unknown language '%s'\n", params.language.c_str());
		whisper_print_usage(argc, argv, params);
		exit(0);
	}

	// -- Whisper STT initialisation -----------------------------------------------
	// Loads the Whisper model from disk and creates the inference context.
	struct whisper_context_params cparams = whisper_context_default_params();
	cparams.use_gpu = params.use_gpu;

	struct whisper_context *ctx_wsp = whisper_init_from_file_with_params(params.model_wsp.c_str(), cparams);

	if (!ctx_wsp) {
        fprintf(stderr, "No whisper.cpp model specified. Please provide using -mw <modelfile>\n");
        return 1;
    }

	// -- llama-server connection check --------------------------------------------
	fprintf(stderr, "\n");
	fprintf(stderr, "  Connecting to llama-server at %s ...\n", params.llama_url.c_str());

	bool server_ok = false;
	for (int attempt = 0; attempt < 3; attempt++) {
		if (llama_server_health_check(params.llama_url)) {
			server_ok = true;
			break;
		}
		fprintf(stderr, "  Attempt %d/3 failed, retrying in 2s...\n", attempt + 1);
		std::this_thread::sleep_for(std::chrono::seconds(2));
	}

	if (server_ok) {
		fprintf(stderr, "  llama-server is ready.\n\n");
	} else {
		fprintf(stderr, "  WARNING: llama-server not responding at %s\n", params.llama_url.c_str());
		fprintf(stderr, "  The assistant will start but LLM requests will fail until the server is available.\n\n");
	}

	// Just do no translation for now
	params.language = "en";
	params.translate = false;

	// -- Audio capture initialisation ---------------------------------------------
	// Sets up the SDL audio capture device with a 15-second ring buffer,
	// or loads a WAV file for automated test mode.
	bool test_mode = !params.test_input_file.empty();
	std::vector<float> test_audio_data;
	bool test_audio_injected = false;

	if (test_mode) {
		std::vector<std::vector<float>> test_audio_stereo;
		if (!read_wav(params.test_input_file, test_audio_data, test_audio_stereo, false)) {
			fprintf(stderr, "%s: failed to read test input file: %s\n", __func__, params.test_input_file.c_str());
			return 1;
		}
	}

	audio_async audio(15 * 1000); // length_ms
	if (!test_mode) {
		if (!audio.init(params.capture_id, WHISPER_SAMPLE_RATE))
		{
			fprintf(stderr, "%s: audio.init() failed!\n", __func__);
			return 1;
		}
		audio.resume();
	}

	bool is_running = true;
	bool force_speak = false;

	float prob0 = 0.0f;

	const std::string chat_symb = ":";

	std::vector<float> pcmf32_cur;
	std::vector<float> pcmf32_prev;
	std::vector<float> pcmf32_prompt;

	std::string prompt_whisper;
	if (params.language == "ru")
		std::string prompt_whisper = ::replace(k_prompt_whisper_ru, "{1}", "Anna");
	else
		std::string prompt_whisper = ::replace(k_prompt_whisper, "{1}", params.bot_name);

	// construct the initial prompt for LLaMA inference
	std::string prompt_llama = params.prompt.empty() ? k_prompt_llama : params.prompt;

	// Initialize tool calling system early (needed for prompt injection)
	tool_system::ToolRegistry& tool_registry = tool_system::ToolRegistry::getInstance();
	std::string tools_json_path = "custom/talk-llama/tools/tools.json";
	if (!tool_registry.loadFromFile(tools_json_path)) {
		fprintf(stderr, "WARNING: Failed to load tools from %s\n", tools_json_path.c_str());
	} else {
		tool_system::registerBuiltinExecutors(tool_registry);
		fprintf(stdout, "[Tool System] Loaded %zu tools from %s\n", tool_registry.getAllTools().size(), tools_json_path.c_str());
	}

	// Initialize Wyoming client for voice control tools
	std::string wyoming_host;
	int wyoming_port;
	tool_system::WyomingClient* wyoming_client = nullptr;
	if (tool_system::parseWyomingUrl(params.xtts_url, wyoming_host, wyoming_port)) {
		wyoming_client = new tool_system::WyomingClient(wyoming_host, wyoming_port);
		tool_system::g_wyoming_client = wyoming_client;
		fprintf(stdout, "[Wyoming Client] Initialized for %s:%d\n", wyoming_host.c_str(), wyoming_port);
	} else {
		fprintf(stderr, "WARNING: Failed to parse Wyoming URL: %s\n", params.xtts_url.c_str());
	}

	// -- Instruct preset loading --------------------------------------------------
	// Loads a JSON preset file that defines system/user/bot message formatting,
	// stop sequences, and other instruct-tuned model parameters.
	if (!params.instruct_preset.empty())
	{
		try
		{
			std::string filename = "instruct_presets/" + params.instruct_preset + ".json";
			nlohmann::json jsonData;
			std::ifstream jsonFile(filename);

			if (jsonFile.is_open())
			{
				jsonFile >> jsonData;
				jsonFile.close();
				params.instruct_preset_data = jsonData;
			}
			else
			{ // not found
				std::cout << "Warning: preset file '" << filename << "' does not exist. Turning off instruct mode" << std::endl;
				params.instruct_preset = "";
			}
		}
		catch (const std::exception &e)
		{
			std::cerr << "Error parsing JSON: " << e.what() << std::endl;
			return 1;
		}
	}
	else // not passed
	{
		params.instruct_preset = "";
	}

	// need to have leading ' '
	prompt_llama.insert(0, 1, ' ');

	prompt_llama = ::replace(prompt_llama, "{0}", params.person);
	prompt_llama = ::replace(prompt_llama, "{1}", params.bot_name);

	{
		// get time string
		std::string time_str;
		{
			time_t t = time(0);
			struct tm *now = localtime(&t);
			char buf[128];
			strftime(buf, sizeof(buf), "%H:%M", now);
			time_str = buf;
		}
		prompt_llama = ::replace(prompt_llama, "{2}", time_str);
	}

	{
		// get year string
		std::string year_str;
		std::string ymd;
		{
			time_t t = time(0);
			struct tm *now = localtime(&t);
			char buf[128];
			strftime(buf, sizeof(buf), "%Y", now);
			year_str = buf;
			strftime(buf, sizeof(buf), "%Y-%m-%d", now);
			ymd = buf;
		}
		prompt_llama = ::replace(prompt_llama, "{3}", year_str);
		prompt_llama = ::replace(prompt_llama, "{5}", ymd);
	}

	prompt_llama = ::replace(prompt_llama, "{4}", chat_symb);

	// Inject tool definitions into prompt (for Mistral tool calling)
	if (tool_registry.getAllTools().size() > 0) {
		std::string tools_prompt = tool_registry.getToolsPrompt();
		prompt_llama += "\n\n" + tools_prompt;
		fprintf(stdout, "[Tool System] Injected %zu tools into system prompt\n", tool_registry.getAllTools().size());
	}

	// -- Conversation history management ------------------------------------------
	// Instead of token arrays, we maintain the full conversation as a string.
	// Each turn appends "Person: text\nBot: response\n" to the history.
	// The full prompt sent to llama-server = prompt_llama + conversation_history.
	std::string conversation_history;

	if (params.verbose_prompt)
	{
		fprintf(stdout, "\n");
		fprintf(stdout, "%s", prompt_llama.c_str());
		fflush(stdout);
	}

	// show wake command if enabled
	const std::string wake_cmd = params.wake_cmd;
	const int wake_cmd_length = get_words(wake_cmd).size();
	const bool use_wake_cmd = wake_cmd_length > 0;

	if (use_wake_cmd)
	{
		printf("%s : the wake-up command is: '%s%s%s'\n", __func__, "\033[1m", wake_cmd.c_str(), "\033[0m");
	}

	// clear audio buffer
	audio.clear();

	// text inference variables
	const int voice_id = 2;

	std::string text_heard_prev;
	std::string text_heard_trimmed;
	int new_command_allowed = 1;
	std::string google_resp;
	std::vector<std::string> tts_intros;
	std::string rand_intro_text = "";
	std::string last_output_buffer = "";
	std::string last_output_needle = "";
	if (params.language == "ru")
	{
		tts_intros = {"Hm", "Nu", "Nuu", "O", "A", "A?", "Ugu", "Okh", "Ha", "Akh"};
	}
	else
	{
		tts_intros = {"Hm", "Hmm", "Well", "Well well", "Huh", "Ugh", "Uh", "Um", "Mmm", "Oh", "Ooh", "Haha", "Ha ha", "Ahh", "Whoa", "Really", "I mean", "By the way", "Anyway", "So", "Actually", "Uh-huh", "Seriously", "Whatever", "Ahh", "Like", "But", "You know", "Wait", "Ahem", "Damn", params.person};
	}
	srand(time(NULL)); // Initialize the random number generator

	int last_command_time = 0;
	std::string current_voice = params.xtts_voice;

	// -- Antiprompt / stop-word setup ---------------------------------------------
	// Builds the list of strings that signal the end of a bot turn.
	std::vector<std::string> antiprompts = {
		params.person + chat_symb,
		params.person + " " + chat_symb,
	};
	if (!params.allow_newline)
		antiprompts.push_back("\n");
	if (!params.instruct_preset_data["stop_sequence"].empty())
		antiprompts.push_back(params.instruct_preset_data["stop_sequence"]);
	if (!params.instruct_preset_data["bot_message_suffix"].empty())
	{
		antiprompts.push_back(params.instruct_preset_data["bot_message_suffix"]);
		antiprompts.push_back("</end_of_turn>");
	}

	// additional stop words
	size_t startIndex = 0;
	size_t endIndex = params.stop_words.find(';');
	if (params.stop_words.size())
	{
		if (endIndex == std::string::npos) // single word
		{
			antiprompts.push_back(params.stop_words);
		}
		else
		{
			while (startIndex < params.stop_words.size()) // multiple stop-words
			{
				std::string word = params.stop_words.substr(startIndex, endIndex - startIndex);
				if (word.size())
				{
					word = ::replace(word, "\\r", "\r");
					word = ::replace(word, "\\n", "\n");
					antiprompts.push_back(word);
				}
				startIndex = endIndex + 1;
				endIndex = params.stop_words.find(';', startIndex);
				if (endIndex == std::string::npos)
					endIndex = params.stop_words.size();
			}
		}
	}
	printf("Llama stop words: ");
	for (const auto &prompt : antiprompts)
		printf("'%s', ", prompt.c_str());

	std::thread input_thread(input_thread_func);
#ifdef HOTKEYS
	std::thread shortcut_thread([cur_window_handle]()
								{ keyboard_shortcut_func(cur_window_handle); });
#endif
	printf("\nVoice commands: Stop (say 'stop' or type it)\n");

	// -- TTS connection warmup ----------------------------------------------------
	// Sends an initialisation phrase to Wyoming-Piper to verify connectivity
	// and warm up the TTS pipeline before the first user interaction.
	printf("\n=========================================\n");
	printf("Testing Wyoming-Piper TTS Connection...\n");
	printf("=========================================\n");
	printf("TTS URL: %s\n", params.xtts_url.c_str());
	printf("TTS Voice: %s\n", params.xtts_voice.c_str());
	printf("LLM URL: %s\n", params.llama_url.c_str());

	// Pause microphone during TTS test to prevent feedback
	if (!test_mode) {
		audio.pause();
		printf("(Microphone paused during TTS test)\n");
	}

	// Send a simple test message to Wyoming-Piper
	std::thread tts_test_thread([&params]() {
		send_tts_async("Voice assistant initialized", params.xtts_voice, params.language, params.xtts_url, 0, params.debug);
	});
	tts_test_thread.detach();

	// Wait for TTS test audio to finish playing (avoid feedback)
	std::this_thread::sleep_for(std::chrono::milliseconds(3000));
	printf("TTS test sent. If you heard audio, TTS is working.\n");
	printf("=========================================\n\n");

	// Resume microphone
	if (!test_mode) {
		audio.resume();
		printf("(Microphone resumed)\n");
	}

	// -- Tool system status display -----------------------------------------------
	// Lists all loaded tools and whether each supports fast-path (pre-LLM) execution.
	printf("\n=========================================\n");
	printf("Tool Calling System Status\n");
	printf("=========================================\n");
	if (tool_registry.getAllTools().size() > 0) {
		printf("Tool system initialized with %zu tools\n", tool_registry.getAllTools().size());

		// List available tools
		for (const auto& tool : tool_registry.getAllTools()) {
			printf("  - %s%s\n", tool.name.c_str(), tool.fast_path ? " (fast path)" : "");
		}
	} else {
		printf("No tools loaded (tool calling disabled)\n");
	}
	printf("=========================================\n\n");

	if (params.push_to_talk)
		printf("Type anything or hold 'Alt' to speak:\n");
	else
		printf("Start speaking or typing:\n");

	printf("\n\n");
	printf("%s%s ", params.person.c_str(), chat_symb.c_str());
	fflush(stdout);
	int vad_result_prev = 2; // ended
	double speech_start_ms = 0;
	double speech_end_ms = 0;
	double speech_len = 0;
	int len_in_samples = 0;
	std::string all_heard_pre;
	double llama_start_time = 0.0;
	double llama_end_time = 0.0;
	double llama_time_total = 0.0;
	double llama_start_generation_time = 0.0;
	std::string user_typed = "";
	bool user_typed_this = false;

	// ===========================================================================
	// Main listen -> transcribe -> generate -> speak loop.
	// Runs continuously until SIGINT, SIGTERM, or SDL quit event.
	// ===========================================================================
	while (is_running)
	{
		// Check for signal
		if (g_sigint_received) {
			fprintf(stderr, "Signal received, exiting main loop...\n");
			g_stop_generation = true; // abort any in-flight CURL stream
			is_running = false;
			break;
		}

		// handle Ctrl + C
		is_running = sdl_poll_events();

		if (!is_running)
		{
			break;
		}

		// delay
		std::this_thread::sleep_for(std::chrono::milliseconds(50));

		int64_t t_ms = 0;

#ifdef HOTKEYS
		// keyboard input
		user_typed_this = false;
		console::set_display(console::reset);
		if (!input_queue.empty())
		{
			std::string buffer;
			while (!input_queue.empty())
			{
				buffer += input_queue.front() + "\n";
				input_queue.pop();
			}
			user_typed = buffer;
			trim(user_typed);
			user_typed_this = true;
		}

		// hotkeys
		if (g_hotkey_pressed.size())
		{
			if (g_hotkey_pressed == "Ctrl+Space")
			{
				user_typed = "Stop";
			}
			else if (g_hotkey_pressed == "Escape")
			{
				// IMMEDIATE STOP: Bypass VAD and Whisper entirely for <100ms latency
				printf(" [Escape - Immediate Stop!]\n");
				send_tts_async("stop", params.xtts_voice, params.language, params.xtts_url, 0, params.debug);
				audio.clear();
				g_hotkey_pressed = "";
				continue;
			}
			else if (g_hotkey_pressed == "Ctrl+Right")
			{
				user_typed = "Regenerate";
			}
			else if (g_hotkey_pressed == "Ctrl+Delete")
			{
				user_typed = "Delete";
			}
			else if (g_hotkey_pressed == "Ctrl+R")
			{
				user_typed = "Reset";
			}

			if (g_hotkey_pressed != "Alt")
			{
				user_typed_this = true;
				g_hotkey_pressed = "";
			}
		}
#endif
		// -- Audio capture --------------------------------------------------------
		// Gets the latest 1-second chunk of microphone audio (or injects test audio).
		{
			// In test mode, inject the test audio data once
			if (test_mode && !test_audio_data.empty()) {
				pcmf32_cur = test_audio_data;
				test_audio_data.clear(); // Use only once
				test_audio_injected = true;
			} else if (!test_mode) {
				audio.get(1000, pcmf32_cur); // step_ms, async - reduced to 1s for better responsiveness
			}

			// -- Voice Activity Detection (VAD) -----------------------------------
			// Determines whether speech has started or ended in the captured audio.
			// Includes smart early-stop detection for short high-energy commands like "stop".
			int vad_result;
			if (test_mode && test_audio_injected && !pcmf32_cur.empty()) {
				// Simulate VAD: speech started then ended
				if (vad_result_prev != 1) {
					vad_result = 1; // Speech started
				} else {
					vad_result = 2; // Speech ended - trigger processing
				}
			} else {
				bool is_speech = !::vad_simple(pcmf32_cur, WHISPER_SAMPLE_RATE, params.vad_last_ms, params.vad_thold, params.freq_thold, params.print_energy, params.min_energy);

				// SMART EARLY STOP DETECTION
				static double early_trigger_start_time = 0;
				bool early_trigger = false;

				if (is_speech && vad_result_prev != 1) {
					early_trigger_start_time = get_current_time_ms();
				} else if (is_speech && vad_result_prev == 1) {
					double speech_duration_ms = get_current_time_ms() - early_trigger_start_time;

					int check_samples = std::min((int)pcmf32_cur.size(), (WHISPER_SAMPLE_RATE * 500) / 1000);
					float recent_energy = 0.0f;
					for (int i = pcmf32_cur.size() - check_samples; i < (int)pcmf32_cur.size(); i++) {
						recent_energy += fabsf(pcmf32_cur[i]);
					}
					recent_energy /= check_samples;

					if (speech_duration_ms >= 300.0 && speech_duration_ms <= 600.0 && recent_energy > 0.01f) {
						early_trigger = true;
						if (params.print_energy) {
							fprintf(stderr, "\n[Early Stop Trigger: dur=%.0fms, energy=%.6f]\n", speech_duration_ms, recent_energy);
						}
					}
				}

				if (is_speech) {
					if (early_trigger) {
						vad_result = 2; // Trigger early end for interrupt commands
					} else {
						vad_result = 1;
					}
				} else {
					vad_result = (vad_result_prev == 1) ? 2 : 0;
				}
			}
			if (vad_result == 1 && params.vad_start_thold) // speech started
			{
				if (vad_result_prev != 1) // real start
				{
					speech_start_ms = get_current_time_ms();
					vad_result_prev = 1;

					// whisper warmup request
					if (!test_mode && (!params.push_to_talk || (params.push_to_talk && g_hotkey_pressed == "Alt")))
					{
						const int min_samples_warmup = WHISPER_SAMPLE_RATE;
						if (pcmf32_cur.size() < (size_t)min_samples_warmup) {
							pcmf32_cur.resize(min_samples_warmup, 0.0f);
						}

						{
							all_heard_pre = ::trim(::transcribe(ctx_wsp, params, pcmf32_cur, prompt_whisper, prob0, t_ms));
							g_hotkey_pressed = "";
						}
					}
				}
			}
			// -- Speech ended: transcribe and process ---------------------------------
			// Triggered when VAD detects end-of-speech, force_speak flag, or typed input.
			// Runs Whisper transcription then dispatches the result to the command/LLM pipeline.
if (vad_result >= 2 && vad_result_prev == 1 || force_speak || user_typed.size()) // speech ended or user typed
			{
				speech_end_ms = get_current_time_ms();
				speech_len = speech_end_ms - speech_start_ms;
				if (speech_len < 0.10)
					speech_len = 0;
				else if (speech_len > 10.0)
					speech_len = 0;
				if (params.debug) {
					printf("%.3f found vad length: %.2f\n", get_current_time_ms(), speech_len);
				}
				vad_result_prev = 2;
				speech_start_ms = 0;

				if (!speech_len && !user_typed.size() && !(test_mode && test_audio_injected))
					continue;

				speech_len = speech_len + 0.3; // front padding
				if (speech_len < 1.10)
					speech_len = 1.10; // whisper doesn't like sentences < 1.10s
				if (!test_mode) {
					int audio_window_ms = g_generation_running.load() ? 2000 : 10000;
					audio.get(audio_window_ms, pcmf32_cur);
				}
				std::string all_heard;
				if (params.debug) {
					printf("%.3f after vad-end (%d)\n", get_current_time_ms(), (int)pcmf32_cur.size());
				}
				if (user_typed.size())
				{
					all_heard = user_typed;
					user_typed = "";
				}
				else if (!force_speak)
				{
					if (!params.push_to_talk || (params.push_to_talk && g_hotkey_pressed == "Alt"))
					{
						const int min_samples = WHISPER_SAMPLE_RATE;
						if (pcmf32_cur.size() < (size_t)min_samples) {
							pcmf32_cur.resize(min_samples, 0.0f);
						}

						if (params.debug) {
							printf("%.3f before transcribe, buffer size: %d\n", get_current_time_ms(), (int)pcmf32_cur.size());
						}
						all_heard = ::trim(::transcribe(ctx_wsp, params, pcmf32_cur, prompt_whisper, prob0, t_ms));
						if (params.debug) {
							printf("%.3f after transcribe, result: '%s'\n", get_current_time_ms(), all_heard.c_str());
						}
						g_hotkey_pressed = "";
					}
				}
				if (params.debug) {
					printf("%.3f after real whisper\n", get_current_time_ms());
				}

				const auto words = get_words(all_heard);

				std::string wake_cmd_heard;
				std::string text_heard;

				for (int i = 0; i < (int)words.size(); ++i)
				{
					if (i < wake_cmd_length)
					{
						wake_cmd_heard += words[i] + " ";
					}
					else
					{
						text_heard += words[i] + " ";
					}
				}
				if (params.print_energy)
					fprintf(stdout, " [text_heard: (%s)]\n", text_heard.c_str());

				// check if audio starts with the wake-up command if enabled
				if (use_wake_cmd)
				{
					const float sim = similarity(wake_cmd_heard, wake_cmd);

					if ((sim < 0.7f) || (text_heard.empty()))
					{
						audio.clear();
						continue;
					}
				}

				// optionally give audio feedback that the current text is being processed
				if (!params.heard_ok.empty())
				{
					int ret = system((params.speak + " " + std::to_string(voice_id) + " '" + params.heard_ok + "'").c_str());
					if (ret != 0)
					{
						fprintf(stderr, "%s: failed to speak\n", __func__);
					}
				}
				//  remove text between brackets using regex
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
				if (params.language == "en" && !user_typed_this)
					text_heard = std::regex_replace(text_heard, std::regex("[^a-zA-Z0-9\\.,\\?!\\s\\:\\'\\-]"), "");
				// take first line
				text_heard = text_heard.substr(0, text_heard.find_first_of('\n'));

				// remove leading and trailing whitespace
				text_heard = std::regex_replace(text_heard, std::regex("^\\s+"), "");
				text_heard = std::regex_replace(text_heard, std::regex("\\s+$"), "");

				// misheard text, sometimes whisper is hallucinating
				text_heard = RemoveTrailingCharactersUtf8(text_heard, U"!");
				text_heard = RemoveTrailingCharactersUtf8(text_heard, U",");
				text_heard = RemoveTrailingCharactersUtf8(text_heard, U".");
				text_heard = RemoveTrailingCharactersUtf8(text_heard, U"\u00BB");
				text_heard = RemoveTrailingCharactersUtf8(text_heard, U"[");
				text_heard = RemoveTrailingCharactersUtf8(text_heard, U"]");
				if (!text_heard.empty() && text_heard[0] == '.')
					text_heard.erase(0, 1);
				if (!text_heard.empty() && text_heard[0] == '!')
					text_heard.erase(0, 1);
				if (!text_heard.empty() && text_heard[0] == '[')
					text_heard.erase(0, 1);
				trim(text_heard);
				// Hallucination filter
				if (text_heard == "!" || text_heard == "." || text_heard == "Sil" || text_heard == "Bye" || text_heard == "Okay" || text_heard == "Okay." || text_heard == "Thank you." || text_heard == "Thank you" || text_heard == "Thanks." || text_heard == "Bye." || text_heard == "Thank you for listening." || text_heard == params.bot_name || text_heard.find("End of") != std::string::npos || text_heard.find("The End") != std::string::npos || text_heard.find("THE END") != std::string::npos || text_heard.find("Thanks for watching") != std::string::npos || text_heard.find("Thank you for watching") != std::string::npos || text_heard.find("Silence") != std::string::npos || text_heard == "You're" || text_heard == "you're" || text_heard == "You're not" || text_heard == "See?" || text_heard == "you" || text_heard == "You" || text_heard == "Yeah" || text_heard == "Well" || text_heard == "Hey" || text_heard == "Oh" || text_heard == "Right" || text_heard == "Real" || text_heard == "Huh" || text_heard == "I" || text_heard == "I'm" || text_heard == "*")
					text_heard = "";
				text_heard = std::regex_replace(text_heard, std::regex("\\s+$"), ""); // trailing whitespace

				text_heard_trimmed = text_heard; // no periods or spaces
				trim(text_heard_trimmed);
				if (!text_heard_trimmed.empty() && text_heard_trimmed[0] == '.')
					text_heard_trimmed.erase(0, 1);
				if (!text_heard_trimmed.empty() && text_heard_trimmed[0] == '!')
					text_heard_trimmed.erase(0, 1);
				if (!text_heard_trimmed.empty()) {
					if (text_heard_trimmed[text_heard_trimmed.length() - 1] == '.' || text_heard_trimmed[text_heard_trimmed.length() - 1] == '!')
						text_heard_trimmed.erase(text_heard_trimmed.length() - 1, 1);
				}
				trim(text_heard_trimmed);
				text_heard_trimmed = LowerCase(text_heard_trimmed);

				fflush(stdout);

				// TTS rand INTRO sentence for instant response
				if (params.xtts_intro)
				{
					if (text_heard_trimmed.size())
					{
						rand_intro_text = tts_intros[rand() % tts_intros.size()];
						text_to_speak_arr[thread_i] = rand_intro_text;
						int current_thread_idx = thread_i;
						threads.emplace_back([&, current_thread_idx]
											 {
							if (text_to_speak_arr[current_thread_idx].size())
							{
								send_tts_async(text_to_speak_arr[current_thread_idx], current_voice, params.language, params.xtts_url, 0, params.debug);
								text_to_speak_arr[current_thread_idx] = "";
							} });
						thread_i++;
					}
				}

				// -- Fast-path tool execution -----------------------------------------
				// Checks if the heard text matches a registered fast-path tool (e.g. "stop").
				// If matched, executes the tool immediately and skips LLM generation entirely.
				auto [matched, tool_def] = tool_registry.matchFastPath(text_heard);
				// Skip resume_speaking if we're not actually paused — pass through to LLM
				bool skip_fast_path = (tool_def.name == "resume_speaking" && !tool_system::g_wyoming_paused);
				if (matched && tool_def.fast_path && !skip_fast_path) {
					fprintf(stdout, "\n[Fast Path Tool: %s]\n", tool_def.name.c_str());

					tool_system::ToolResult result = tool_registry.execute(tool_def.name, json::object());

					if (result.success) {
						// Stop any background generation
						g_stop_generation = true;
						// Speak confirmation via a direct TTS call (bypasses stopped generation)
						if (!result.message.empty()) {
							send_tts_async(result.message, params.xtts_voice, params.language, params.xtts_url, 0, params.debug);
						}
						audio.clear();
						g_hotkey_pressed = "";
						test_audio_injected = false;
						continue;
					} else {
						fprintf(stderr, "Fast path tool execution failed: %s\n", result.message.c_str());
						// Fall through to normal processing
					}
				}

				// If generation is already running, only fast-path commands are accepted above
				if (g_generation_running.load()) {
					audio.clear();
					continue;
				}

				// Join previous generation thread before starting a new one
				if (g_llm_thread.joinable()) {
					g_llm_thread.join();
				}

				// -- Background generation thread -------------------------------------
				// Spawns g_llm_thread to run LLM inference via llama-server HTTP
				// and TTS dispatch concurrently, allowing the main thread to
				// return immediately to listening for new commands.
				g_stop_generation = false;
				g_generation_running = true;
				// Tell Wyoming-Piper a new response is starting so it resets STOP_CMD.
				if (tool_system::g_wyoming_client)
					tool_system::g_wyoming_client->sendNewResponse();
				g_llm_thread = std::thread([&, text_heard]() mutable {

				llama_start_time = get_current_time_ms();

				if (text_heard.empty() || force_speak)
				{
					fprintf(stdout, "%s: Heard nothing, skipping ...\n", __func__);
					g_hotkey_pressed = "";
					test_audio_injected = false;
					g_generation_running = false;
					return;
				}

				force_speak = false;
				test_audio_injected = false;
				trim(text_heard);
				if (params.debug) {
					fprintf(stdout, "text_heard %s:\n", text_heard.c_str());
				}

				text_heard_prev = text_heard;

				// Print user input
				if (user_typed_this)
				{
					fprintf(stdout, "%s%s%s", "\033[1m", (params.bot_name + chat_symb).c_str(), "\033[0m");
				}
				else
				{
					fprintf(stdout, "%s%s%s", "\033[1m",
						("\n" + params.person + chat_symb + " " + text_heard + "\n" + params.bot_name + chat_symb).c_str(),
						"\033[0m");
				}
				fflush(stdout);

				// Build the full prompt for llama-server:
				// system_prompt + conversation_history + new_user_turn
				std::string user_turn = "\n" + params.person + chat_symb + " " + text_heard;
				std::string bot_prefix = "\n" + params.bot_name + chat_symb;

				// Build the full prompt
				std::string full_prompt = prompt_llama + conversation_history + user_turn + bot_prefix;

				// removing all threads
				if (threads.size() >= 80)
				{
					printf("[!...");
					for (auto &t : threads)
					{
						try
						{
							if (t.joinable())
								t.join();
						}
						catch (const std::exception &ex)
						{
							std::cerr << "[Exception]: Failed join a thread: " << ex.what() << '\n';
						}
					}
					threads.clear();
					printf("]");
				}
				if (thread_i > 100)
					thread_i = 0; // rotation

				// Initialize tool call parser for this generation
				tool_system::ToolCallParser tool_parser;
				tool_parser.reset();

				// Set up the streaming context
				llama_stream_context stream_ctx;
				stream_ctx.stop_flag = &g_stop_generation;
				stream_ctx.new_tokens = 0;
				stream_ctx.debug = params.debug;
				stream_ctx.params = &params;
				stream_ctx.current_voice = current_voice;
				stream_ctx.threads = &threads;
				stream_ctx.text_to_speak_arr = text_to_speak_arr;
				stream_ctx.reply_part_arr = reply_part_arr;
				stream_ctx.thread_i = &thread_i;
				stream_ctx.reply_part = &reply_part;
				stream_ctx.tool_parser = &tool_parser;
				stream_ctx.tool_registry = &tool_registry;
				stream_ctx.antiprompts = &antiprompts;
				stream_ctx.done = false;

				// Build stop words for the server request
				std::vector<std::string> server_stop_words;
				for (const auto& ap : antiprompts) {
					server_stop_words.push_back(ap);
				}
				// Always include these for Mistral format
				server_stop_words.push_back("[INST]");
				server_stop_words.push_back("</s>");

				llama_start_generation_time = get_current_time_ms();

				// Send to llama-server and stream response
				std::string response = llama_server_generate(
					full_prompt,
					params.llama_url,
					params,
					g_stop_generation,
					server_stop_words,
					stream_ctx
				);

				// Clean response: remove antiprompt text from the stored response
				for (const auto& ap : antiprompts) {
					size_t apos = response.find(ap);
					if (apos != std::string::npos) {
						response = response.substr(0, apos);
					}
				}
				trim(response);

				// Append this turn to conversation history
				conversation_history += user_turn + bot_prefix + " " + response;

				llama_end_time = get_current_time_ms();
				if (params.verbose)
				{
					llama_time_total = llama_end_time - llama_start_time;
					double llama_time_gen = llama_end_time - llama_start_generation_time;
					printf("\n\n[tokens: %d out in %.3f s = %.2f t/s]\n",
						stream_ctx.new_tokens, llama_time_gen,
						stream_ctx.new_tokens / (llama_time_gen > 0 ? llama_time_gen : 1.0));
				}
				llama_start_generation_time = 0.0;
				g_hotkey_pressed = "";

				// In test mode, exit after processing one input
				if (test_mode) {
					fprintf(stderr, "\n%s: TEST MODE - processing complete, waiting for TTS threads\n", __func__);
					for (auto& t : threads) {
						if (t.joinable()) {
							t.join();
						}
					}
					_exit(0);
				}
				g_generation_running = false;
			}); // end g_llm_thread lambda
			continue; // main thread returns to listen loop
			} // end if(vad_result >= 2) - main thread path
		}
	}

	if (!test_mode) {
		audio.pause();
	}

	whisper_print_timings(ctx_wsp);
	whisper_free(ctx_wsp);

	// Stop background LLM thread before cleanup to prevent std::terminate()
	if (g_llm_thread.joinable()) {
		g_stop_generation = true;
		if (g_sigint_received) {
			// On SIGINT, detach rather than join — the CURL stream may be mid-transfer
			// and join() would block waiting for the next chunk. The OS cleans up on exit.
			g_llm_thread.detach();
		} else {
			g_llm_thread.join();
		}
	}

	// In test mode, or on SIGINT, don't wait for input threads
	if (!test_mode && !g_sigint_received) {
		input_thread.join();
#ifdef HOTKEYS
		shortcut_thread.join();
#endif
	}

	// Cleanup Wyoming client
	if (wyoming_client) {
		delete wyoming_client;
		tool_system::g_wyoming_client = nullptr;
	}

	return 0;
}

// -------------------------------------------------------------------------
// Platform entry points
// -------------------------------------------------------------------------
#if _WIN32
int wmain(int argc, const wchar_t **argv_UTF16LE)
{
	console::init(true, true);
	atexit([]()
		   { console::cleanup(); });
	std::vector<std::string> buffer(argc);
	std::vector<const char *> argv_UTF8(argc);
	for (int i = 0; i < argc; ++i)
	{
		buffer[i] = console::UTF16toUTF8(argv_UTF16LE[i]);
		argv_UTF8[i] = buffer[i].c_str();
	}
	return run(argc, argv_UTF8.data());
}
#else
int main(int argc, const char **argv_UTF8)
{
	console::init(true, true);
	atexit([]()
		   { console::cleanup(); });
	return run(argc, argv_UTF8);
}
#endif
