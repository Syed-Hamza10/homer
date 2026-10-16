import { Route, Routes } from "react-router"
import { AppShell } from "@/components/AppShell"
import { ApprovalsPage } from "@/features/approvals/ApprovalsPage"
import { AuthGuard } from "@/features/auth/AuthGuard"
import { LoginPage } from "@/features/auth/LoginPage"
import { ChatPage } from "@/features/chat/ChatPage"
import { PrivacyPage } from "@/features/privacy/PrivacyPage"

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
