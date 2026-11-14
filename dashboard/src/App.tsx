import { lazy, Suspense } from "react"
import { Route, Routes } from "react-router"
import { AppShell } from "@/components/AppShell"
import { AuthGuard } from "@/features/auth/AuthGuard"
import { LoginPage } from "@/features/auth/LoginPage"
import { ChatPage } from "@/features/chat/ChatPage"

const TodayPage = lazy(() =>
  import("@/features/today/TodayPage").then((page) => ({
    default: page.TodayPage,
  })),
)
const InboxPage = lazy(() =>
  import("@/features/inbox/InboxPage").then((page) => ({
    default: page.InboxPage,
  })),
)
const CalendarPage = lazy(() =>
  import("@/features/calendar/CalendarPage").then((page) => ({
    default: page.CalendarPage,
  })),
)
const ApprovalsPage = lazy(() =>
  import("@/features/approvals/ApprovalsPage").then((page) => ({
    default: page.ApprovalsPage,
  })),
)
const PrivacyPage = lazy(() =>
  import("@/features/privacy/PrivacyPage").then((page) => ({
    default: page.PrivacyPage,
  })),
)
const SettingsPage = lazy(() =>
  import("@/features/settings/SettingsPage").then((page) => ({
    default: page.SettingsPage,
  })),
)

export default function App() {
  return (
    <Suspense fallback={null}>
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
    </Suspense>
  )
}
