// Tags: free-form labels on transactions. They look like the pigeonhole tab label, in ink tones.
import { useId, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { t } from '../i18n'

const clean = (s) => s.replace(/\s+/g, ' ').trim().slice(0, 80)
const same = (a, b) => a.toLowerCase() === b.toLowerCase()

export function TagPill({ name, onRemove, small }) {
  return (
    <span className={`tag ${small ? 'sm' : ''}`}>
      <i aria-hidden="true" />{name}
      {onRemove && <button type="button" className="tag-x" onClick={onRemove} aria-label={t('Remove tag {name}', { name })}><X /></button>}
    </span>
  )
}

export function TagList({ tags, max = 3 }) {
  if (!tags?.length) return null
  const shown = tags.slice(0, max)
  return (
    <span className="tag-list">
      {shown.map((tg) => <TagPill key={tg.id ?? tg.name} name={tg.name} small />)}
      {tags.length > max && <span className="tag sm more">+{tags.length - max}</span>}
    </span>
  )
}

// Chips plus a text box with suggestions from the household's tags. Enter or comma adds; a new name creates a tag on save.
// It follows the ARIA combobox pattern: the list is announced as it opens, arrows move the active option.
export function TagInput({ value, onChange, known = [], placeholder, single = false, label, labelledBy, describedBy }) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1) // -1: nothing picked with the arrow keys, Enter takes the typed text
  const input = useRef(null)
  const closing = useRef(null)
  const listId = useId()
  const suggestions = useMemo(() => {
    const q = text.trim().toLowerCase()
    return known.filter((k) => !value.some((v) => same(v, k.name)) && (!q || k.name.toLowerCase().includes(q))).slice(0, 8)
  }, [text, known, value])
  const typed = clean(text)
  const showCreate = typed && !known.some((k) => same(k.name, typed)) && !value.some((v) => same(v, typed))
  const options = [...suggestions.map((s) => s.name), ...(showCreate ? [typed] : [])]

  const add = (name) => {
    let n = clean(name)
    if (!n) return
    n = known.find((k) => same(k.name, n))?.name ?? n // reuse the existing spelling
    if (!value.some((v) => same(v, n))) onChange(single ? [n] : [...value, n])
    setText('')
    setActive(-1)
  }
  const onKey = (e) => {
    if ((e.key === 'Enter' || e.key === ',') && (text.trim() || active >= 0)) {
      e.preventDefault()
      add(active >= 0 ? options[active] : text)
    } else if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, options.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, -1)) }
    else if (e.key === 'Escape' && open && options.length) { e.stopPropagation(); setOpen(false); setActive(-1) }
    else if (e.key === 'Backspace' && !text && value.length) onChange(value.slice(0, -1))
  }

  const expanded = open && options.length > 0
  const remove = (v) => {
    onChange(value.filter((x) => x !== v))
    requestAnimationFrame(() => input.current?.focus()) // the chip and its button are gone; stay in the box
  }
  return (
    <div className="tag-input" onClick={(e) => e.target === e.currentTarget && input.current?.focus()}>
      {value.map((v) => <TagPill key={v} name={v} onRemove={() => remove(v)} />)}
      {!(single && value.length) && (
        <input ref={input} value={text} placeholder={value.length ? '' : (placeholder ?? t('Add a tag…'))}
          aria-label={labelledBy ? undefined : label ?? t('Tags')} aria-labelledby={labelledBy} aria-describedby={describedBy}
          role="combobox" aria-expanded={expanded} aria-controls={listId} aria-autocomplete="list"
          aria-activedescendant={expanded && active >= 0 ? `${listId}-${active}` : undefined}
          onChange={(e) => { setText(e.target.value); setOpen(true); setActive(-1) }} onKeyDown={onKey}
          onFocus={() => { clearTimeout(closing.current); setOpen(true) }}
          onBlur={() => { if (text.trim()) add(text); closing.current = setTimeout(() => setOpen(false), 120) }} />
      )}
      {/* Always in the page so aria-controls points at something; hidden while closed. */}
      <ul className="tag-menu" id={listId} role="listbox" aria-label={t('Tag suggestions')} hidden={!expanded}>
        {expanded && options.map((o, i) => (
            <li key={o} id={`${listId}-${i}`} role="option" aria-selected={i === active} className={i === active ? 'on' : ''}
              onMouseDown={(e) => { e.preventDefault(); add(o) }} onMouseEnter={() => setActive(i)}>
              {showCreate && i === options.length - 1 ? <>{t('Create tag')} <TagPill name={o} small /></> : <TagPill name={o} small />}
            </li>
          ))}
      </ul>
    </div>
  )
}
