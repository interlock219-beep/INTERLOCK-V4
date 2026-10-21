import { Icon } from './Icon';

const FLOW = [
  {
    state: 'done',
    title: 'Incident detected',
    detail: 'Agent modified 4 files',
    time: '10:24:11',
  },
  {
    state: 'done',
    title: 'Changes analysed',
    detail: '3 risky operations identified',
    time: '10:24:32',
  },
  { state: 'done', title: 'Recovery plan created', detail: '4 actions, 0 conflicts', time: '10:25:06' },
  {
    state: 'active',
    title: 'Verification complete',
    detail: 'All data restored · no residue',
    time: '10:28:17',
  },
];

/**
 * Illustrative product panel for the hero. Everything shown here is a static
 * mock of a simulated run — it is labelled as such and performs no actions.
 */
export function HeroMock() {
  return (
    <div className="mock-window" aria-label="Illustrative recovery dashboard preview" role="img">
      <div className="mock-head">
        <Icon name="shield" width={15} height={15} style={{ color: 'var(--yellow)' }} />
        Interlock · recovery flow
        <span style={{ marginLeft: 'auto', color: 'var(--text-faint)' }}>simulated preview</span>
      </div>
      <div className="mock-body">
        <div className="mock-main">
          <div className="mock-title">
            Recovery Flow <span>PID 4127</span>
          </div>
          <ul className="flow">
            {FLOW.map((item) => (
              <li key={item.title} className={`flow-item ${item.state}`}>
                <span className="flow-dot">
                  <Icon name={item.state === 'active' ? 'eye' : 'check'} />
                </span>
                <span>
                  <span className="flow-title">{item.title}</span>
                  <br />
                  <span className="flow-detail">{item.detail}</span>
                </span>
                <span className="flow-time">{item.time}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="mock-side">
          <div className="spark">
            <svg viewBox="0 0 200 60" aria-hidden="true">
              <polyline
                points="0,48 25,44 50,45 75,32 100,34 125,22 150,25 175,12 200,14"
                fill="none"
                stroke="#FFD900"
                strokeWidth="2"
              />
              <polyline
                points="0,54 25,52 50,53 75,50 100,49 125,47 150,46 175,44 200,43"
                fill="none"
                stroke="#46b17b"
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
            </svg>
            <div className="stat-caption" style={{ marginTop: 6 }}>
              restored vs. expected
            </div>
          </div>

          <div className="mock-stat">
            <p className="mock-stat-title">Files restored</p>
            <ul>
              <li>
                <Icon name="check" /> 4 files
              </li>
              <li>
                <Icon name="check" /> 0 conflicts
              </li>
              <li>
                <Icon name="check" /> 0 residue
              </li>
            </ul>
          </div>

          <div className="mock-success">
            <Icon name="check-circle" />
            <span>
              <strong>Recovery successful</strong>
              <span>Integrity verified against captured evidence.</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HeroMock;
