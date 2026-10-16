import { Route, Routes } from "react-router"
import { AuthGuard } from "@/features/auth/AuthGuard"
import { LoginPage } from "@/features/auth/LoginPage"
import { ChatPage } from "@/features/chat/ChatPage"

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route path="/" element={<ChatPage />} />
      </Route>
    </Routes>
  )
}
