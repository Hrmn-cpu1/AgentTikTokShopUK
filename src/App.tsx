import { Component, type ReactNode } from 'react';
import ConnectionGate from './ConnectionGate';

class FailClosedBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? <main className="server-workspace" role="alert"><h1>Dados indisponíveis</h1>
          <p>As operações ficam bloqueadas até verificar o servidor.</p></main>
      : this.props.children;
  }
}

export default function App() {
  return <FailClosedBoundary><ConnectionGate /></FailClosedBoundary>;
}
