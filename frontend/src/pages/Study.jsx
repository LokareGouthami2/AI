import { useState } from 'react';
import { useParams } from 'react-router-dom';
import Flashcards from '../study/Flashcards.jsx';
import Quiz from '../study/Quiz.jsx';
import AskDocument from '../study/AskDocument.jsx';

export default function Study() {
  const { id } = useParams();
  const [tab, setTab] = useState('ask');
  return (
    <div className="stack">
      <div className="segmented" role="group" aria-label="Study tools">
        <button aria-pressed={tab === 'ask'} onClick={() => setTab('ask')}>Ask your document</button>
        <button aria-pressed={tab === 'flashcards'} onClick={() => setTab('flashcards')}>Flashcards</button>
        <button aria-pressed={tab === 'quiz'} onClick={() => setTab('quiz')}>Quiz</button>
      </div>
      {tab === 'ask' && <AskDocument docId={id} />}
      {tab === 'flashcards' && <Flashcards docId={id} />}
      {tab === 'quiz' && <Quiz docId={id} />}
    </div>
  );
}
