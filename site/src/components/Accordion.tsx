import { useId, useState, type ReactNode } from 'react';
import { Icon } from './Icon';

interface AccordionItemData {
  id: string;
  question: string;
  answer: ReactNode;
}

/** HTML ids cannot contain spaces or punctuation; callers may pass prose. */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function Accordion({ items }: { items: AccordionItemData[] }) {
  const base = useId();
  const [openId, setOpenId] = useState<string | null>(items[0]?.id ?? null);

  return (
    <div className="accordion">
      {items.map((item) => {
        const open = openId === item.id;
        const safe = slugify(item.id) || 'item';
        const triggerId = `${base}-${safe}-trigger`;
        const panelId = `${base}-${safe}-panel`;
        return (
          <div className="accordion-item" key={item.id}>
            <h3 className="mb-0">
              <button
                type="button"
                id={triggerId}
                className="accordion-trigger"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setOpenId(open ? null : item.id)}
              >
                {item.question}
                <Icon name="chevron-down" className="chev" width={18} height={18} />
              </button>
            </h3>
            <div
              id={panelId}
              role="region"
              aria-labelledby={triggerId}
              className="accordion-panel"
              hidden={!open}
            >
              {item.answer}
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface TabData {
  id: string;
  label: string;
  content: ReactNode;
}

/**
 * WAI-ARIA tabs: roving arrow-key navigation, Home/End support, and a single
 * tab stop. Only the selected panel is rendered, keeping page JS light.
 */
export function Tabs({
  tabs,
  label,
  initialId,
}: {
  tabs: TabData[];
  label: string;
  initialId?: string;
}) {
  const base = useId();
  const [active, setActive] = useState(initialId ?? tabs[0]?.id);

  const move = (delta: number) => {
    const index = tabs.findIndex((tab) => tab.id === active);
    const next = (index + delta + tabs.length) % tabs.length;
    setActive(tabs[next].id);
    document.getElementById(`${base}-tab-${tabs[next].id}`)?.focus();
  };

  return (
    <div>
      <div className="tabs" role="tablist" aria-label={label}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`${base}-tab-${tab.id}`}
            className="tab-btn"
            aria-selected={active === tab.id}
            aria-controls={`${base}-panel-${tab.id}`}
            tabIndex={active === tab.id ? 0 : -1}
            onClick={() => setActive(tab.id)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                event.preventDefault();
                move(1);
              } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                event.preventDefault();
                move(-1);
              } else if (event.key === 'Home') {
                event.preventDefault();
                setActive(tabs[0].id);
              } else if (event.key === 'End') {
                event.preventDefault();
                setActive(tabs[tabs.length - 1].id);
              }
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${base}-panel-${tab.id}`}
          aria-labelledby={`${base}-tab-${tab.id}`}
          hidden={active !== tab.id}
          tabIndex={0}
        >
          {active === tab.id ? tab.content : null}
        </div>
      ))}
    </div>
  );
}

export default Accordion;
