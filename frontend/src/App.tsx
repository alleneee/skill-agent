import Chat from './pages/Chat';
import { ErrorBoundary } from './components/ErrorBoundary';

function App() {
  return (
    <ErrorBoundary>
      <Chat />
    </ErrorBoundary>
  );
}

export default App;
