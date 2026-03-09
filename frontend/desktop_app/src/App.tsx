import "./App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import VideoChat from "./components/VideoChat";
import AvatarListPage from "./pages/AvatarListPage";
import AvatarCreatePage from "./pages/AvatarCreatePage";
import AvatarDetailPage from "./pages/AvatarDetailPage";

function App() {
  return (
    <BrowserRouter>
      <main className="w-screen h-screen bg-gray-800">
        <Routes>
          <Route path="/" element={<VideoChat />} />
          <Route path="/avatars" element={<AvatarListPage />} />
          <Route path="/avatars/create" element={<AvatarCreatePage />} />
          <Route path="/avatars/:id" element={<AvatarDetailPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export default App;
