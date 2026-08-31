import React, { useState, useRef } from 'react';
import { Mic, Square } from 'lucide-react';

interface VoiceRecorderProps {
  onAudioRecorded: (blob: Blob) => void;
  disabled?: boolean;
  className?: string;
}

export const VoiceRecorder: React.FC<VoiceRecorderProps> = ({
  onAudioRecorded,
  disabled = false,
  className = '',
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
      alert('Microphone access denied or not supported.');
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
    <div className={`flex items-center gap-3 ${className}`}>
      <button
        type="button"
        onClick={toggleRecording}
        disabled={disabled}
        className={`relative flex items-center justify-center gap-2 px-5 h-[38px] rounded-full font-semibold text-xs transition-colors shrink-0 ${
          isRecording
            ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-md'
            : 'bg-[#1e1b4b] hover:bg-[#312e81] text-indigo-300 border border-[#4338ca] hover:border-indigo-400'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        {isRecording ? (
          <>
            <Square className="w-3.5 h-3.5 fill-white" />
            <span>Finish Recording</span>
          </>
        ) : (
          <>
            <Mic className="w-3.5 h-3.5 text-indigo-400" />
            <span>Voice Reasoning</span>
          </>
        )}
      </button>

      {isRecording && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-900 border border-rose-500 text-xs text-rose-400">
          <span className="w-2 h-2 rounded-full bg-rose-500"></span>
          <span>Listening to your thoughts...</span>
        </div>
      )}
    </div>
  );
};
