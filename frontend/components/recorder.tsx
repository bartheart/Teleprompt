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
    const [error, setError] = useState<string | null>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const startInFlightRef = useRef(false);
    const wasActiveRef = useRef(false);
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
            autoConnect: false,
            reconnection: false,
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



    const stopRecording = useCallback(() => {
        startInFlightRef.current = false;
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
            mediaRecorderRef.current.stop();
        }
        mediaRecorderRef.current = null;

        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
        }
        streamRef.current = null;

        if (socket.current?.connected) {
            socket.current.disconnect();
        }
        setIsRecording(false);
    }, []);

    const startRecording = useCallback(async () => {
        if (startInFlightRef.current || isRecording || mediaRecorderRef.current) {
            return;
        }

        startInFlightRef.current = true;
        setError(null);
        try {
            const stream: MediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });
            streamRef.current = stream;

            const mimeType = getCompatibleMime();
            if (!mimeType) {
                throw new Error("No supported audio MIME type found");
            }

            const recorder = new MediaRecorder(stream, { mimeType });
            mediaRecorderRef.current = recorder;

            recorder.onstart = () => setIsRecording(true);
            recorder.onstop = () => setIsRecording(false);
            recorder.onerror = () => {
                setError("Recorder error occurred while capturing audio.");
                setIsRecording(false);
            };
            recorder.ondataavailable = (event) => {
                if (socket.current?.connected && event.data.size > 0) {
                    socket.current.emit("audio_data", event.data);
                }
            };

            recorder.start(100);
            if (recorder.state !== "recording") {
                throw new Error("Recorder failed to start.");
            }

            initializeSocket();
            if (socket.current) {
                socket.current.connect();
                socket.current.emit("start_session", {
                    context,
                    predictionCount,
                });
                socket.current.emit("mime_type", mimeType);
            }
        } catch (err) {
            const message = (err as Error).message || "Failed to start microphone.";
            setError(message);
            stopRecording();
        } finally {
            startInFlightRef.current = false;
        }
    }, [context, predictionCount, initializeSocket, isRecording, stopRecording]);

    useEffect(() => {
        if (active && !wasActiveRef.current) {
            void startRecording();
        }
        if (!active && wasActiveRef.current) {
            stopRecording();
        }
        wasActiveRef.current = active;
    }, [active, startRecording, stopRecording]);

    useEffect(() => {
        return () => {
            stopRecording();
            socket.current = null;
        };
    }, [stopRecording]);

    return (
        <div>
            <div className="status-row">
                <p className={`pill ${isConnected ? "ok" : "warn"}`}>
                    Socket: {isConnected ? "Connected" : "Disconnected"}
                </p>
                <p className={`pill ${isRecording ? "ok" : ""}`}>
                    Recorder: {isRecording ? "Recording" : "Idle"}
                </p>
            </div>
            {error && <p className="error">{error}</p>}
        </div>
    );
};
