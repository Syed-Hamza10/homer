export type Event = {
  event_id: string
  title: string
  start: string
  end: string
  location: string
  attendees: string[]
}

export type Slot = { start: string; end: string }
