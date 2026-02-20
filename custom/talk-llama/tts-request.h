#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cjson/cJSON.h>

#define TTS_REQUEST_TYPE "type"
#define TTS_REQUEST_DATA "data"
#define TTS_REQUEST_DATA_LENGTH "data_length"
#define TTS_REQUEST_PAYLOAD_LENGTH "payload_length"
#define TTS_REQUEST_NEWLINE "\n"
#define TTS_REQUEST_VERSION "version"
#define TTS_REQUEST_VERSION_NUMBER "1.5.3"

#ifdef __cplusplus
extern "C" {
#endif

// Take in a string to be spoken and return a JSON encoded request for the TTS Server
//NOTE: Returns a pointer to a string allocated by this function, you are required to free it after use.
char *TTS_RequestEncode(const char *textToSpeak);

#ifdef __cplusplus
}
#endif