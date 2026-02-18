// tts-socket-test.c
// Test TTS Socket library

#include "tts-socket.h"
#include "tts-request.h"

//main driver program
int main(int argc, char *argv[])
{
    int hSocket, read_size;
    struct sockaddr_in server;
    char SendToServer[100] = {0};
    char server_reply[200] = {0};
    char *json = TTS_RequestEncode("Hello world");

    //Create socket
    hSocket = TTS_SocketCreate();
    if(hSocket == -1)
    {
        printf("Could not create socket\n");
        return 1;
    }
    printf("Socket is created\n");
    //Connect to remote server
    if (TTS_SocketConnect(hSocket) < 0)
    {
        perror("connect failed.\n");
        return 1;
    }
    printf("Sucessfully conected with server\n");
    printf("Sending request to server:\n");
    printf("%s\n", json);
    // gets(SendToServer);
    //Send data to the server
    TTS_SocketSend(hSocket, json, strlen(json));
    free(json);
    //Received the data from the server
    // read_size = SocketReceive(hSocket, server_reply, 200);
    // printf("Server Response : %s\n\n",server_reply);
    close(hSocket);
    shutdown(hSocket,0);
    shutdown(hSocket,1);
    shutdown(hSocket,2);
    return 0;
}