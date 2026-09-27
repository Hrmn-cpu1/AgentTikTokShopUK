import { Component, type ReactNode } from 'react';
import ConnectionGate from './ConnectionGate';
import ServerWorkspace from './ServerWorkspace';

class FailClosedBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? <main className="server-workspace" role="alert"><h1>Business truth unavailable</h1>
          <p>The operator workspace is blocked until its server state can be checked.</p></main>
      : this.props.children;
  }
}

export default function App() {
  return <FailClosedBoundary><ConnectionGate><ServerWorkspace /></ConnectionGate></FailClosedBoundary>;
}
