import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Chat from './pages/Chat';
import Knowledge from './pages/Knowledge';
import Debug from './pages/Debug';
import { ErrorBoundary } from './components/ErrorBoundary';

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/debug" element={<Debug />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
