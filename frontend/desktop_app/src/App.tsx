import { useEffect } from "react";
import "./App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import VideoChat from "./components/VideoChat";
import AvatarListPage from "./pages/AvatarListPage";
import AvatarCreatePage from "./pages/AvatarCreatePage";
import AvatarDetailPage from "./pages/AvatarDetailPage";
import AvatarSelectionPage from "./pages/AvatarSelectionPage";
import { registerServiceWorker } from "./service-worker-registration";

function App() {
  // 注册 PWA Service Worker
  useEffect(() => {
    registerServiceWorker();
  }, []);

  return (
    <BrowserRouter>
      <main className="w-screen h-screen bg-gray-800">
        <Routes>
          <Route path="/" element={<AvatarListPage />} />
          <Route path="/videochat" element={<VideoChat />} />
          <Route path="/avatars" element={<AvatarListPage />} />
          <Route path="/avatars/create" element={<AvatarCreatePage />} />
          <Route path="/avatars/:id" element={<AvatarDetailPage />} />
          <Route path="/select-avatar" element={<AvatarSelectionPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export default App;
