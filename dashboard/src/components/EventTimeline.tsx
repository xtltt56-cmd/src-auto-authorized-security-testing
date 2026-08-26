import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { EventLevel, TaskEvent } from '../lib/types'

type EventTimelineProps = {
  events: TaskEvent[]
}

const levelLabels: Record<'all' | EventLevel, string> = {
  all: '全部',
  info: '信息',
  success: '成功',
  warning: '警告',
  danger: '阻止/失败',
}

const levelIcons: Record<EventLevel, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: ShieldAlert,
}

export function EventTimeline({ events }: EventTimelineProps) {
  const [filter, setFilter] = useState<'all' | EventLevel>('all')
  const [selectedEvent, setSelectedEvent] = useState<TaskEvent | null>(null)
  const visibleEvents = useMemo(
    () => (filter === 'all' ? events : events.filter((event) => event.level === filter)),
    [events, filter],
  )

  return (
    <section className="surface-panel event-panel" aria-labelledby="event-title">
      <div className="panel-header">
        <div>
          <h4 id="event-title">实时事件</h4>
          <p>消息已脱敏，关闭页面不会终止任务</p>
        </div>
        <label className="filter-control">
          <span>筛选</span>
          <select aria-label="事件等级筛选" value={filter} onChange={(event) => setFilter(event.target.value as 'all' | EventLevel)}>
            {(Object.keys(levelLabels) as Array<'all' | EventLevel>).map((key) => <option key={key} value={key}>{levelLabels[key]}</option>)}
          </select>
        </label>
      </div>
      <div className="event-list">
        {visibleEvents.length === 0 ? <div className="empty-state">当前筛选没有事件</div> : visibleEvents.map((event) => {
          const Icon = levelIcons[event.level]
          return (
            <button
              className="event-row"
              type="button"
              key={event.id}
              aria-pressed={selectedEvent?.id === event.id}
              onClick={() => setSelectedEvent(event)}
            >
              <span className="event-icon" data-level={event.level}><Icon size={16} aria-hidden="true" /></span>
              <span className="event-copy">
                <strong>{event.message}</strong>
                <small>{event.stage}{event.tool ? ` · ${event.tool}` : ''}</small>
              </span>
              <time dateTime={event.time}>{event.time}</time>
            </button>
          )
        })}
      </div>
      {selectedEvent ? (
        <div className="event-detail" role="region" aria-labelledby="event-detail-title">
          <div className="event-detail-heading">
            <div>
              <h5 id="event-detail-title">事件详情</h5>
              <p>{selectedEvent.stage}{selectedEvent.tool ? ` · ${selectedEvent.tool}` : ''}</p>
            </div>
            <time dateTime={selectedEvent.time}>{selectedEvent.time}</time>
          </div>
          <p className="event-detail-message">{selectedEvent.message}</p>
          <small>证据已脱敏；该记录仅描述本地任务状态，不会触发新的网络请求。</small>
        </div>
      ) : null}
    </section>
  )
}
