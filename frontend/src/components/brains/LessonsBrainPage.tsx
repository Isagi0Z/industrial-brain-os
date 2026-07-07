import React from 'react';
import { Lightbulb } from 'lucide-react';
import { BrainChat } from './BrainChat';

export const LessonsBrainPage: React.FC = () => (
  <BrainChat
    title="Lessons Learned Brain"
    icon={Lightbulb}
    description="Answers from previously captured incidents and operator lessons — abstracting field experience into reusable knowledge linked to assets."
    endpoint="/api/v1/brain/lessons/chat"
    suggestions={[
      'What lessons have we learned from bearing failures?',
      'Are there past incidents involving seal leaks on pumps?',
      'What operational mistakes should we avoid on cooling systems?',
    ]}
  />
);
