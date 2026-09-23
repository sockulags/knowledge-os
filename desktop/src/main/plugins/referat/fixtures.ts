// Synthetic Referat meetings for the plugin's tests. No real meeting data.

import type { Meeting, MeetingSummary } from 'referat-sdk'

export const PROTOKOLL_MARKDOWN = `# Protokoll – Planeringsmöte

## Sammanfattning

Teamet planerade nästa kvartal.

## Beslut

- Vi byter till Postgres för lagringen.
- Releasen flyttas till fredag.
  - Gäller bara webbversionen.
- Kundmötet hålls på plats.

## Actionpunkter

- Bengt skriver migreringsplanen.

## Öppna frågor

- Behöver vi en ny server?
`

export function summary(overrides: Partial<MeetingSummary> = {}): MeetingSummary {
  return {
    id: 'sum-1',
    fileName: 'protocol-protokoll.md',
    templateId: 'protokoll',
    templateName: 'Protokoll',
    focus: '',
    createdAt: '2026-09-20T13:00:00.000Z',
    markdown: PROTOKOLL_MARKDOWN,
    legacy: false,
    ...overrides
  }
}

export function meeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: '20260920120000-abc123',
    title: 'Planeringsmöte',
    createdAt: '2026-09-20T12:00:00.000Z',
    durationSec: 47 * 60,
    status: 'done',
    folder: '/synthetic/meetings/20260920120000-abc123',
    inProgress: false,
    artifacts: { transcript: true, summaries: 1, audioFiles: 1, levels: false },
    transcript: {
      language: 'sv',
      text: 'Hej allihop. Vi börjar.',
      segments: [
        { startSec: 0, endSec: 2, text: 'Hej allihop.', speaker: 'S1' },
        { startSec: 65, endSec: 67, text: 'Vi börjar.', speaker: 'S2' }
      ],
      speakers: { S1: 'Anna' }
    },
    summaries: [summary()],
    audioFiles: ['/synthetic/meetings/20260920120000-abc123/audio.webm'],
    ...overrides
  }
}
