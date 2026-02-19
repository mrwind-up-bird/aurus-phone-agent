"use client";

import { useEffect, useRef } from "react";
import type { AgentState } from "@/lib/types";

interface AudioVisualizerProps {
  state: AgentState;
  audioTrack?: MediaStreamTrack | null;
}

const STATE_COLORS: Record<string, [string, string]> = {
  idle: ["#334155", "#1e293b"],
  initializing: ["#334155", "#1e293b"],
  listening: ["#3b82f6", "#1d4ed8"],
  thinking: ["#f59e0b", "#d97706"],
  speaking: ["#22c55e", "#16a34a"],
  filler: ["#8b5cf6", "#7c3aed"],
};

export function AudioVisualizer({ state, audioTrack }: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);
  const analyserRef = useRef<AnalyserNode | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // HiDPI
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const width = rect.width;
    const height = rect.height;

    let audioContext: AudioContext | null = null;

    if (audioTrack) {
      audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(
        new MediaStream([audioTrack])
      );
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 128;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;
    }

    const barCount = 40;
    const dataArray = new Uint8Array(barCount);

    function draw() {
      if (!canvas || !ctx) return;

      ctx.clearRect(0, 0, width, height);

      if (analyserRef.current && state !== "idle" && state !== "initializing") {
        analyserRef.current.getByteFrequencyData(dataArray);
      } else {
        const time = Date.now() / 1000;
        for (let i = 0; i < barCount; i++) {
          const center = barCount / 2;
          const dist = Math.abs(i - center) / center;
          const base = state === "idle" || state === "initializing" ? 8 : 35;
          const wave = Math.sin(time * 1.8 + i * 0.4) * (15 - dist * 8);
          const wave2 = Math.cos(time * 2.5 + i * 0.7) * 8;
          const noise = Math.random() * (state === "thinking" ? 25 : 6);
          dataArray[i] = Math.min(
            255,
            Math.max(0, base + wave + wave2 + noise - dist * 15)
          );
        }
      }

      const totalGap = width * 0.25;
      const barWidth = (width - totalGap) / barCount;
      const gap = totalGap / (barCount + 1);

      const [color1, color2] = STATE_COLORS[state] || STATE_COLORS.idle;

      for (let i = 0; i < barCount; i++) {
        const val = dataArray[i] / 255;
        const barHeight = Math.max(2, val * height * 0.75);
        const x = gap + i * (barWidth + gap);
        const y = (height - barHeight) / 2;

        // Gradient per bar
        const grad = ctx.createLinearGradient(x, y, x, y + barHeight);
        grad.addColorStop(0, color1);
        grad.addColorStop(1, color2);
        ctx.fillStyle = grad;
        ctx.globalAlpha = 0.35 + val * 0.65;

        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
        ctx.fill();

        // Glow on active bars
        if (val > 0.4 && state !== "idle") {
          ctx.shadowColor = color1;
          ctx.shadowBlur = 12;
          ctx.globalAlpha = val * 0.3;
          ctx.beginPath();
          ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
          ctx.fill();
          ctx.shadowBlur = 0;
        }
      }

      ctx.globalAlpha = 1;
      animationRef.current = requestAnimationFrame(draw);
    }

    draw();

    return () => {
      cancelAnimationFrame(animationRef.current);
      analyserRef.current = null;
      audioContext?.close();
    };
  }, [state, audioTrack]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded-xl"
      style={{ height: 100 }}
    />
  );
}
