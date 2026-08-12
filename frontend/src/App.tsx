import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Store from './pages/Store';
import Chat from './pages/Chat';
import Explorer from './pages/Explorer';
import Conversations from './pages/Conversations';
import Admin from './pages/Admin';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Store />} />
          <Route path="/assistant" element={<Chat />} />
          <Route path="/explorer" element={<Explorer />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
