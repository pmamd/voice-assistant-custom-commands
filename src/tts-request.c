#include "tts-request.h"

// Take in a string to be spoken and return a JSON encoded request for the TTS Server
//NOTE: Returns a pointer to a string allocated by this function, you are required to free it after use.
char *TTS_RequestEncode(const char *textToSpeak)
{
    // Example request
    // const char *json = "{\"type\": \"synthesize\", \"version\": \"1.5.3\", \"data_length\": 62}\n{\"text\": \"Hello world\", \"voice\": {\"name\": \"en_US-amy-medium\"}}";

    cJSON *payload = cJSON_CreateObject();
    cJSON *header;
    char *payloadString = NULL;
    char *headerString = NULL;
    char *returnString = NULL;

    // 1) JSON Encode textToSpeak as "text" for payload 
    if (cJSON_AddStringToObject(payload, "text", textToSpeak) == NULL)
    {
        return NULL;
    }
    payloadString = cJSON_PrintUnformatted(payload);
    if (payloadString == NULL)
    {
        fprintf(stderr, "Failed to print payload.\n");
        return NULL;
    } 
    else {
        //printf("payload: %s\n", payloadString);
    }
    cJSON_Delete(payload);

    // 2) Create header with
        // "type" : "synthesize"
        // "version" : TTS_REQUEST_VERSION_NUMBER
        // "data_length" : strlen(payload)
    header = cJSON_CreateObject();
    if (cJSON_AddStringToObject(header, TTS_REQUEST_TYPE, "synthesize") == NULL)
    {
        return NULL;
    }
    if (cJSON_AddStringToObject(header, TTS_REQUEST_VERSION, TTS_REQUEST_VERSION_NUMBER) == NULL)
    {
        return NULL;
    }
    if (cJSON_AddNumberToObject(header, TTS_REQUEST_DATA_LENGTH, strlen(payloadString)) == NULL)
    {
        return NULL;
    }
    headerString = cJSON_PrintUnformatted(header);
    if (headerString == NULL)
    {
        fprintf(stderr, "Failed to print header.\n");
        return NULL;
    }
    else {
        //printf("header: %s\n", headerString);
    }

    // 3) Postpend NEWLINE and payload to header
    // +2: one for newline, one for null terminator
    returnString = (char*)malloc(strlen(headerString) + strlen(payloadString) + 2);
    strcpy(returnString, headerString);
    strcat(returnString, TTS_REQUEST_NEWLINE);
    strcat(returnString, payloadString);

    cJSON_Delete(header);
    free(headerString);
    free(payloadString);

    return returnString;
}
