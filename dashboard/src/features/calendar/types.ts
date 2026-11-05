import type { WallTime } from "@/lib/zoned"

export type Person = {
  email: string
  name: string
  response: string
  organizer: boolean
}

export type CalendarEvent = {
  id: string
  title: string
  start: string
  end: string
  all_day: boolean
  location: string
  description: string
  attendees: string[]
  people: Person[]
  organizer: string
  video_link: string
}

export type EventRange = {
  events: CalendarEvent[]
  source: string
}

export type Slot = { start: string; end: string }

export type View = "day" | "week" | "month"

export type DateOnly = Pick<WallTime, "year" | "month" | "day">

export type EventFields = {
  title: string
  start: string
  end: string
  attendees: string[]
  description: string
  location: string
}

export type FormValue = {
  title: string
  date: string
  start: string
  end: string
  attendees: string
  description: string
  location: string
}
