"use client";
import React, { useCallback, useEffect, useState, useRef } from "react";
import { Socket, io } from "socket.io-client";

type RecorderProps = {
  context: string;
  predictionCount: number;
  onTranscript: (text: string) => void;
  onPredictions: (items: string[]) => void;
  active: boolean;
};

export default function Recorder({
  context,
  predictionCount,
  onTranscript,
  onPredictions,
  active,
}: RecorderProps) {
    const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
    const [error, setError] = useState<string | null>(null);
    const audioRef = useRef<MediaRecorder | null>(null);
    const [isRecording, setIsRecording] = useState<boolean>(false);
    const socket = useRef<Socket | null >(null);
    const [isConnected, setIsConnected] = useState<boolean>(false);

    const getCompatibleMime = () => {
        const types = [
            'audio/webm',
            'audio/webm;codecs=opus',
            'audio/mp4',
            'audio/mp4;codecs=opus',
            'audio/ogg',
            'audio/ogg;codecs=opus'
        ];

        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }

        return null;
    };

    const initializeSocket = useCallback(() => {
        if (socket.current) return;

        const newSocket = io("http://127.0.0.1:8000", {
            transports: ['websocket'],
            autoConnect: true,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
        });

        newSocket.on('connect_error', (error) => {
            console.error('Socket connection error:', error);
            setError(`Socket error: ${error.message}`);
        });

        newSocket.on('connect', () => {
            setIsConnected(true);
        })

        newSocket.on('disconnect', () => {
            setIsConnected(false);
        });

        newSocket.on("transcription", (response: { text?: string }) => {
            if (response?.text) {
                onTranscript(response.text);
            }
        });

        newSocket.on("predictions", (response: { items?: string[] }) => {
            onPredictions(response?.items ?? []);
        });

        newSocket.on("server_error", (response: { message?: string }) => {
            setError(response?.message ?? "Unknown server error");
        });
       
        socket.current = newSocket
    }, [onPredictions, onTranscript]);



    const startRecording = useCallback((stream: MediaStream) => {
        if (!stream) return;

        try {
            const mimeType = getCompatibleMime();

            if (!mimeType){
                throw new Error("No supported audio MIME type found");
            }

            initializeSocket();
            if (socket.current) {
                socket.current.connect();
                socket.current.emit("start_session", {
                    context,
                    predictionCount,
                });
                socket.current.emit('mime_type', mimeType);
            };

            const options = { 
                mimeType: mimeType,
                audioBitsPerSecond: 16000,  
                channelCount: 1 
            };

            const recordedMedia = new MediaRecorder(stream, options);
            audioRef.current = recordedMedia;

            recordedMedia.ondataavailable = (event) => {
                const audioChunk = event.data;
                if (socket.current?.connected && audioChunk.size > 0){
                    socket.current.emit('audio_data', audioChunk)
                }
            };

            recordedMedia.start(100);

            setIsRecording(true);

        } catch (err) {
            setError("Error starting recording: " + (err as Error).message);
            console.error("Error starting recording:", err);
        }
    }, [context, predictionCount, initializeSocket]);


    const cleanUp = useCallback(() => {
        if (audioRef.current?.state === 'recording') {
            audioRef.current.stop();
        };
        audioRef.current = null;

        if (audioStream) {
            audioStream.getTracks().forEach((track) => track.stop());
            setAudioStream(null);
        };

        if (socket.current?.connected) {
            socket.current.disconnect();
        }

        setIsRecording(false);

    }, [audioStream]);

    const handleButton = useCallback(async (shouldStart: boolean) => {
        if (!shouldStart && isRecording) {
            cleanUp();
        } else {
            try {
                const stream: MediaStream = await navigator.mediaDevices.getUserMedia({ 
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
                setAudioStream(stream);
                await startRecording(stream);
    
            } catch (err) {
                const errorMessage = (err as Error).message || "An unknown eror";
                setError(errorMessage);
            };
            
        } 
    }, [cleanUp, isRecording, startRecording]);

    useEffect(() => {
        if (active && !isRecording) {
            void handleButton(true);
        } else if (!active && isRecording) {
            void handleButton(false);
        }
    }, [active, isRecording, handleButton]);

    useEffect (() => {
        
        return () => {
            cleanUp();
            socket.current = null;
        };
    }, [cleanUp]);

    return (
        <div>
            <div>
                <p>Socket status: {isConnected ? 'Connected' : 'Disconnected'}</p>
            </div>
            <p>Recorder state: {isRecording ? "Recording" : "Idle"}</p>
            {error && <p>{error}</p>}
        </div>
    );
};
