import { Route, Routes } from "react-router"
import { AppShell } from "@/components/AppShell"
import { ApprovalsPage } from "@/features/approvals/ApprovalsPage"
import { AuthGuard } from "@/features/auth/AuthGuard"
import { LoginPage } from "@/features/auth/LoginPage"
import { CalendarPage } from "@/features/calendar/CalendarPage"
import { ChatPage } from "@/features/chat/ChatPage"
import { InboxPage } from "@/features/inbox/InboxPage"
import { PrivacyPage } from "@/features/privacy/PrivacyPage"
import { SettingsPage } from "@/features/settings/SettingsPage"
import { TodayPage } from "@/features/today/TodayPage"

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/today" element={<TodayPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
