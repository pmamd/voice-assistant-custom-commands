// tts-socket.h
// Function prototypes for socket communication with TTS server

#include<stdio.h>
#include<stdlib.h>
#include<string.h>
#include<sys/socket.h>
#include<arpa/inet.h>
#include<unistd.h>

// Port on which TTS Server is listenting
#define TTS_SERVER_PORT 10200

//Create a Socket for server communication
short TTS_SocketCreate(void);

//try to connect with server
int TTS_SocketConnect(int hSocket);

// Send the data to the server and set the timeout of 20 seconds
int TTS_SocketSend(int hSocket,char* Rqst,short lenRqst);

//receive the data from the server
int TTS_SocketReceive(int hSocket,char* Rsp,short RvcSize);