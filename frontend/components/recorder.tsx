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
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";
    const [error, setError] = useState<string | null>(null);
    const audioContextRef = useRef<AudioContext | null>(null);
    const workletNodeRef = useRef<AudioWorkletNode | null>(null);
    const workletUrlRef = useRef<string | null>(null);
    const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const startInFlightRef = useRef(false);
    const wasActiveRef = useRef(false);
    const [isRecording, setIsRecording] = useState<boolean>(false);
    const socket = useRef<Socket | null >(null);
    const [isConnected, setIsConnected] = useState<boolean>(false);
    const lastAudioSendAtRef = useRef<number | null>(null);
    const audioFrameSeqRef = useRef(0);
    const LOG_EVERY_N_FRAMES = 20;
    const PROCESS_EVERY_SAMPLES = 8000;
    const PCM_CHUNK_SAMPLES = 1024;
    const floatBufferRef = useRef<Float32Array>(new Float32Array(PCM_CHUNK_SAMPLES));
    const floatOffsetRef = useRef(0);
    const batchIdRef = useRef(1);
    const batchSamplesRef = useRef(0);
    const batchStartAtMsRef = useRef<number | null>(null);
    const batchStartByIdRef = useRef<Map<number, number>>(new Map());

    const initializeSocket = useCallback(() => {
        if (socket.current) return;

        const newSocket = io(backendUrl, {
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
                    const now = performance.now();
                    const lastSend = lastAudioSendAtRef.current;
                    const responseBatchId = (response as { batch_id?: number }).batch_id;
                    const nowMs = Date.now();
                    if (typeof responseBatchId === "number") {
                        const batchStart = batchStartByIdRef.current.get(responseBatchId);
                        if (batchStart) {
                            const endToEndMs = nowMs - batchStart;
                            console.info(
                                `[latency] end_to_end_ms=${Math.round(endToEndMs)} batch_id=${responseBatchId}`,
                            );
                            batchStartByIdRef.current.delete(responseBatchId);
                        } else {
                            console.info(
                                `[latency] end_to_end_ms=unknown batch_id=${responseBatchId}`,
                            );
                        }
                    }
                    if (lastSend !== null) {
                        const deltaMs = Math.round(now - lastSend);
                        console.info(
                            `[latency] transcription_delta_ms=${deltaMs} trailing="${trailingWords}"`,
                        );
                    } else {
                        console.info(
                            `[latency] transcription_received trailing="${trailingWords}" (no send timestamp)`,
                        );
                    }
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
    }, [backendUrl, onPredictions, onTranscript]);



    const stopRecording = useCallback(() => {
        startInFlightRef.current = false;

        if (workletNodeRef.current) {
            workletNodeRef.current.port.onmessage = null;
            workletNodeRef.current.disconnect();
        }
        workletNodeRef.current = null;
        if (workletUrlRef.current) {
            URL.revokeObjectURL(workletUrlRef.current);
        }
        workletUrlRef.current = null;

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
        if (startInFlightRef.current || isRecording || workletNodeRef.current) {
            return;
        }

        startInFlightRef.current = true;
        setError(null);
        lastAudioSendAtRef.current = null;
        audioFrameSeqRef.current = 0;
        batchIdRef.current = 1;
        batchSamplesRef.current = 0;
        batchStartAtMsRef.current = null;
        batchStartByIdRef.current.clear();
        floatOffsetRef.current = 0;
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

            const workletSource = `
                class PcmCaptureProcessor extends AudioWorkletProcessor {
                    process(inputs) {
                        const input = inputs[0];
                        if (input && input[0]) {
                            const channel = input[0];
                            this.port.postMessage(channel.slice(0));
                        }
                        return true;
                    }
                }
                registerProcessor("pcm-capture", PcmCaptureProcessor);
            `;
            const workletBlob = new Blob([workletSource], { type: "application/javascript" });
            const workletUrl = URL.createObjectURL(workletBlob);
            workletUrlRef.current = workletUrl;
            await audioContext.audioWorklet.addModule(workletUrl);

            const workletNode = new AudioWorkletNode(audioContext, "pcm-capture");
            workletNodeRef.current = workletNode;

            const handlePcmChunk = (int16: Int16Array) => {
                const currentBatchId = batchIdRef.current;
                if (batchSamplesRef.current === 0) {
                    const batchStartMs = Date.now();
                    batchStartAtMsRef.current = batchStartMs;
                    batchStartByIdRef.current.set(currentBatchId, batchStartMs);
                }
                const now = performance.now();
                lastAudioSendAtRef.current = now;
                audioFrameSeqRef.current += 1;
                const seq = audioFrameSeqRef.current;
                if (seq % LOG_EVERY_N_FRAMES === 0) {
                    console.info(
                        `[latency] audio_pcm_send seq=${seq} samples=${int16.length} batch_id=${currentBatchId}`,
                    );
                }
                batchSamplesRef.current += int16.length;
                if (socket.current?.connected) {
                    socket.current.emit("audio_pcm", {
                        pcm: int16.buffer,
                        client_sent_at_ms: Date.now(),
                        samples: int16.length,
                        batch_id: currentBatchId,
                    });
                }
                while (batchSamplesRef.current >= PROCESS_EVERY_SAMPLES) {
                    const completedBatchId = batchIdRef.current;
                    const batchStartMs = batchStartAtMsRef.current;
                    if (batchStartMs) {
                        const batchCollectMs = Date.now() - batchStartMs;
                        console.info(
                            `[latency] batch_collect_ms=${Math.round(batchCollectMs)} batch_id=${completedBatchId}`,
                        );
                    } else {
                        console.info(
                            `[latency] batch_collect_ms=unknown batch_id=${completedBatchId}`,
                        );
                    }
                    batchSamplesRef.current -= PROCESS_EVERY_SAMPLES;
                    batchIdRef.current += 1;
                    if (batchSamplesRef.current > 0) {
                        const nextBatchStart = Date.now();
                        batchStartAtMsRef.current = nextBatchStart;
                        batchStartByIdRef.current.set(batchIdRef.current, nextBatchStart);
                    } else {
                        batchStartAtMsRef.current = null;
                    }
                }
            };

            workletNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
                const input = event.data;
                if (!input || input.length === 0) {
                    return;
                }
                let offset = floatOffsetRef.current;
                let buffer = floatBufferRef.current;
                for (let i = 0; i < input.length; i += 1) {
                    buffer[offset] = input[i];
                    offset += 1;
                    if (offset === PCM_CHUNK_SAMPLES) {
                        const int16 = new Int16Array(PCM_CHUNK_SAMPLES);
                        for (let j = 0; j < PCM_CHUNK_SAMPLES; j += 1) {
                            const s = Math.max(-1, Math.min(1, buffer[j]));
                            int16[j] = s < 0 ? s * 0x8000 : s * 0x7fff;
                        }
                        handlePcmChunk(int16);
                        offset = 0;
                        buffer = floatBufferRef.current;
                    }
                }
                floatOffsetRef.current = offset;
            };

            source.connect(workletNode);
            workletNode.connect(audioContext.destination);
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
