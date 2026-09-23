import React, { useState, useRef } from 'react';
import { Mic, Square } from 'lucide-react';

interface VoiceRecorderProps {
  onAudioRecorded: (blob: Blob) => void;
  disabled?: boolean;
  className?: string;
  title?: string;
}

export const VoiceRecorder: React.FC<VoiceRecorderProps> = ({
  onAudioRecorded,
  disabled = false,
  className = '',
  title,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        onAudioRecorded(audioBlob);
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Failed to access microphone:', err);
      alert('Доступ к микрофону отклонен или не поддерживается.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <div className={`relative inline-flex items-center shrink-0 ${className}`}>
      <button
        type="button"
        onClick={toggleRecording}
        disabled={disabled}
        title={title || (isRecording ? 'Завершить запись' : 'Голосовой ввод')}
        aria-label={isRecording ? 'Завершить запись' : 'Голосовой ввод'}
        className={`relative w-[38px] h-[38px] rounded-full flex items-center justify-center transition-all cursor-pointer shrink-0 ${
          isRecording
            ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/40 ring-2 ring-rose-400 ring-offset-2 ring-offset-surface-950 animate-pulse'
            : 'bg-[#1e1b4b] hover:bg-[#312e81] text-indigo-300 border border-[#4338ca] hover:border-indigo-400 hover:text-white shadow-sm'
        } ${disabled ? 'opacity-50 cursor-not-allowed pointer-events-none' : 'active:scale-95'}`}
      >
        {isRecording ? (
          <>
            <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-rose-400 rounded-full animate-ping pointer-events-none" />
            <Square className="w-3.5 h-3.5 fill-white text-white" />
          </>
        ) : (
          <Mic className="w-4 h-4 text-indigo-400" />
        )}
      </button>
    </div>
  );
};
