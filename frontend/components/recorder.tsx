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
    const audioContextRef = useRef<AudioContext | null>(null);
    const processorRef = useRef<ScriptProcessorNode | null>(null);
    const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const startInFlightRef = useRef(false);
    const wasActiveRef = useRef(false);
    const [isRecording, setIsRecording] = useState<boolean>(false);
    const socket = useRef<Socket | null >(null);
    const [isConnected, setIsConnected] = useState<boolean>(false);

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

        newSocket.on(
            "transcription",
            (response: { text?: string; current_word?: string; full_text?: string }) => {
                const fullText = response?.full_text?.trim() ?? "";
                const trailingWords = fullText
                    ? fullText.split(/\s+/).slice(-3).join(" ")
                    : (response?.current_word ?? response?.text ?? "").trim();

                if (trailingWords) {
                    onTranscript(trailingWords);
                }
            },
        );

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

        if (processorRef.current) {
            processorRef.current.disconnect();
            processorRef.current.onaudioprocess = null;
        }
        processorRef.current = null;

        if (sourceNodeRef.current) {
            sourceNodeRef.current.disconnect();
        }
        sourceNodeRef.current = null;

        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
        }
        streamRef.current = null;

        if (audioContextRef.current) {
            void audioContextRef.current.close();
        }
        audioContextRef.current = null;

        if (socket.current?.connected) {
            socket.current.disconnect();
        }
        setIsRecording(false);
    }, []);

    const startRecording = useCallback(async () => {
        if (startInFlightRef.current || isRecording || processorRef.current) {
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

            initializeSocket();
            if (socket.current) {
                socket.current.connect();
                socket.current.emit("start_session", {
                    context,
                    predictionCount,
                });
            }

            const audioContext = new AudioContext({ sampleRate: 16000 });
            audioContextRef.current = audioContext;
            const source = audioContext.createMediaStreamSource(stream);
            sourceNodeRef.current = source;

            const processor = audioContext.createScriptProcessor(4096, 1, 1);
            processorRef.current = processor;

            processor.onaudioprocess = (event) => {
                const input = event.inputBuffer.getChannelData(0);
                const int16 = new Int16Array(input.length);
                for (let i = 0; i < input.length; i += 1) {
                    const s = Math.max(-1, Math.min(1, input[i]));
                    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
                }
                if (socket.current?.connected) {
                    socket.current.emit("audio_pcm", int16.buffer);
                }
            };

            source.connect(processor);
            processor.connect(audioContext.destination);
            setIsRecording(true);
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
