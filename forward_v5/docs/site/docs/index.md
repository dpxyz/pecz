<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenClaw — Strategic Project Cockpit</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --color-bg: #f8f9fa;
            --color-surface: #ffffff;
            --color-surface-elevated: #f1f3f5;
            --color-text-primary: #1a1d21;
            --color-text-secondary: #5a636d;
            --color-text-tertiary: #8a929d;
            --color-border: #e3e7eb;
            --color-border-light: #eef1f4;
            --color-accent: #3b6df6;
            --color-accent-light: #e8f0fe;
            --color-success: #0d9e56;
            --color-warning: #e89005;
            --color-error: #dc2626;
            --color-phase-0: #94a3b8;
            --color-phase-active: #3b6df6;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 12px 32px rgba(0,0,0,0.12);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--color-bg);
            color: var(--color-text-primary);
            line-height: 1.6;
            font-size: 15px;
        }

        /* Header */
        .header {
            background: var(--color-surface);
            border-bottom: 1px solid var(--color-border);
            padding: 20px 40px;
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(8px);
        }

        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--color-text-primary);
        }

        .logo span {
            color: var(--color-accent);
        }

        .last-updated {
            font-size: 13px;
            color: var(--color-text-tertiary);
            font-family: 'SF Mono', monospace;
        }

        /* Main Layout */
        .main {
            max-width: 1400px;
            margin: 0 auto;
            padding: 40px;
        }

        /* Section Styling */
        section {
            margin-bottom: 60px;
        }

        .section-title {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            color: var(--color-text-tertiary);
            margin-bottom: 24px;
        }

        /* 1. THE VISION */
        .vision-card {
            background: linear-gradient(135deg, #e8f0fe 0%, #f0f7ff 100%);
            border: 1px solid #d1e0fd;
            border-radius: var(--radius-lg);
            padding: 48px;
            margin-bottom: 20px;
        }

        .vision-title {
            font-size: 32px;
            font-weight: 700;
            letter-spacing: -0.03em;
            margin-bottom: 24px;
            color: var(--color-text-primary);
        }

        .vision-description {
            font-size: 18px;
            line-height: 1.7;
            color: var(--color-text-secondary);
            max-width: 900px;
        }

        .vision-description p {
            margin-bottom: 16px;
        }

        .vision-pillars {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-top: 32px;
        }

        .pillar {
            background: var(--color-surface);
            border-radius: var(--radius-md);
            padding: 24px;
            box-shadow: var(--shadow-sm);
        }

        .pillar-number {
            font-size: 11px;
            font-weight: 600;
            color: var(--color-accent);
            margin-bottom: 8px;
        }

        .pillar-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .pillar-text {
            font-size: 14px;
            color: var(--color-text-secondary);
            line-height: 1.5;
        }

        /* 2. THE TIMELINE - Heart of the Dashboard */
        .timeline-container {
            background: var(--color-surface);
            border-radius: var(--radius-lg);
            padding: 40px;
            box-shadow: var(--shadow-md);
        }

        .timeline-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
        }

        .timeline-title {
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.02em;
        }

        .timeline-legend {
            display: flex;
            gap: 24px;
            font-size: 13px;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--color-text-secondary);
        }

        .legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }

        .legend-dot.complete { background: var(--color-success); }
        .legend-dot.active { background: var(--color-accent); }
        .legend-dot.planned { background: var(--color-border); border: 2px solid var(--color-text-tertiary); }

        .timeline {
            display: flex;
            gap: 16px;
            position: relative;
        }

        .timeline::before {
            content: '';
            position: absolute;
            top: 24px;
            left: 80px;
            right: 40px;
            height: 4px;
            background: linear-gradient(90deg, 
                var(--color-success) 0%, 
                var(--color-success) 45%,
                var(--color-accent) 45%,
                var(--color-accent) 55%,
                var(--color-border) 55%,
                var(--color-border) 100%);
            border-radius: 2px;
            z-index: 0;
        }

        .phase-card {
            flex: 1;
            min-width: 0;
            background: var(--color-surface-elevated);
            border-radius: var(--radius-md);
            padding: 20px;
            position: relative;
            z-index: 1;
            border: 2px solid transparent;
            transition: all 0.2s ease;
        }

        .phase-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
        }

        .phase-card.complete {
            background: #f0fdf4;
            border-color: #bbf7d0;
        }

        .phase-card.active {
            background: var(--color-accent-light);
            border-color: var(--color-accent);
            box-shadow: 0 0 0 3px rgba(59, 109, 246, 0.1);
        }

        .phase-card.blocked {
            opacity: 0.7;
        }

        .phase-indicator {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 16px;
        }

        .phase-card.complete .phase-indicator {
            background: var(--color-success);
            color: white;
        }

        .phase-card.active .phase-indicator {
            background: var(--color-accent);
            color: white;
        }

        .phase-card.planned .phase-indicator {
            background: var(--color-surface);
            color: var(--color-text-tertiary);
            border: 2px solid var(--color-border);
        }

        .phase-name {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 6px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .phase-description {
            font-size: 12px;
            color: var(--color-text-secondary);
            line-height: 1.5;
            margin-bottom: 12px;
        }

        .phase-status {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 20px;
        }

        .phase-status.complete {
            background: #dcfce7;
            color: #166534;
        }

        .phase-status.active {
            background: #dbeafe;
            color: #1e40af;
        }

        .phase-status.planned {
            background: var(--color-border-light);
            color: var(--color-text-tertiary);
        }

        .phase-status.blocked {
            background: #fee2e2;
            color: #991b1b;
        }

        /* Dependency Arrow */
        .dependency-note {
            margin-top: 32px;
            padding: 20px;
            background: #fef3c7;
            border-radius: var(--radius-md);
            border-left: 4px solid var(--color-warning);
            font-size: 14px;
            color: var(--color-text-secondary);
        }

        .dependency-note strong {
            color: var(--color-text-primary);
        }

        /* 3. CURRENT STATUS */
        .current-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
        }

        .current-main {
            background: var(--color-surface);
            border-radius: var(--radius-lg);
            padding: 32px;
            box-shadow: var(--shadow-md);
        }

        .current-header {
            display: flex;
            align-items: flex-start;
            gap: 16px;
            margin-bottom: 24px;
        }

        .current-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--color-accent);
            color: white;
            font-size: 12px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 20px;
        }

        .current-badge::before {
            content: '';
            width: 6px;
            height: 6px;
            background: white;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .current-title {
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 8px;
        }

        .current-subtitle {
            font-size: 15px;
            color: var(--color-text-secondary);
        }

        .workstream-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .workstream-item {
            display: flex;
            align-items: flex-start;
            gap: 16px;
            padding: 16px;
            background: var(--color-surface-elevated);
            border-radius: var(--radius-md);
            border-left: 3px solid transparent;
        }

        .workstream-item.blocked {
            border-left-color: var(--color-error);
        }

        .workstream-item.ready {
            border-left-color: var(--color-success);
        }

        .workstream-item.waiting {
            border-left-color: var(--color-text-tertiary);
        }

        .workstream-icon {
            width: 32px;
            height: 32px;
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            flex-shrink: 0;
        }

        .workstream-icon.blocked { background: #fee2e2; }
        .workstream-icon.ready { background: #dcfce7; }
        .workstream-icon.waiting { background: var(--color-border-light); }

        .workstream-content {
            flex: 1;
        }

        .workstream-name {
            font-weight: 600;
            margin-bottom: 4px;
        }

        .workstream-desc {
            font-size: 13px;
            color: var(--color-text-secondary);
        }

        .current-sidebar {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .sidebar-card {
            background: var(--color-surface);
            border-radius: var(--radius-md);
            padding: 24px;
            box-shadow: var(--shadow-sm);
        }

        .sidebar-title {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--color-text-tertiary);
            margin-bottom: 12px;
        }

        .sidebar-value {
            font-size: 32px;
            font-weight: 700;
            color: var(--color-text-primary);
            margin-bottom: 4px;
        }

        .sidebar-label {
            font-size: 13px;
            color: var(--color-text-secondary);
        }

        /* 4. THE ARCHIVE */
        .archive-container {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 24px;
        }

        .archive-card {
            background: var(--color-surface);
            border-radius: var(--radius-md);
            padding: 24px;
            box-shadow: var(--shadow-sm);
        }

        .archive-card.success { border-top: 3px solid var(--color-success); }
        .archive-card.learning { border-top: 3px solid var(--color-warning); }

        .archive-date {
            font-size: 12px;
            color: var(--color-text-tertiary);
            margin-bottom: 8px;
        }

        .archive-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .archive-desc {
            font-size: 14px;
            color: var(--color-text-secondary);
            line-height: 1.5;
        }

        .archive-tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 20px;
            margin-top: 12px;
        }

        .archive-tag.success { background: #dcfce7; color: #166534; }
        .archive-tag.learning { background: #fef3c7; color: #92400e; }

        /* 5. DEEP DIVE */
        .deep-dive {
            background: var(--color-surface);
            border-radius: var(--radius-lg);
            overflow: hidden;
            box-shadow: var(--shadow-md);
        }

        .deep-dive-header {
            padding: 24px 32px;
            background: var(--color-surface-elevated);
            border-bottom: 1px solid var(--color-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }

        .deep-dive-title {
            font-size: 16px;
            font-weight: 600;
        }

        .deep-dive-toggle {
            font-size: 20px;
            color: var(--color-text-tertiary);
            transition: transform 0.2s ease;
        }

        .deep-dive.expanded .deep-dive-toggle {
            transform: rotate(180deg);
        }

        .deep-dive-body {
            display: none;
            padding: 32px;
        }

        .deep-dive.expanded .deep-dive-body {
            display: block;
        }

        .detail-section {
            margin-bottom: 32px;
        }

        .detail-section:last-child {
            margin-bottom: 0;
        }

        .detail-section-title {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 16px;
            color: var(--color-text-primary);
        }

        .detail-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        .detail-table th {
            text-align: left;
            padding: 12px;
            font-weight: 500;
            color: var(--color-text-tertiary);
            border-bottom: 1px solid var(--color-border);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .detail-table td {
            padding: 12px;
            border-bottom: 1px solid var(--color-border-light);
            color: var(--color-text-secondary);
        }

        .detail-table tr:last-child td {
            border-bottom: none;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 20px;
        }

        .status-badge.pass { background: #dcfce7; color: #166534; }
        .status-badge.fail { background: #fee2e2; color: #991b1b; }
        .status-badge.active { background: #dbeafe; color: #1e40af; }

        .link-list {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }

        .link-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 16px;
            background: var(--color-surface-elevated);
            border-radius: var(--radius-md);
            text-decoration: none;
            color: var(--color-text-primary);
            font-size: 14px;
            transition: all 0.2s ease;
        }

        .link-item:hover {
            background: var(--color-accent-light);
            color: var(--color-accent);
        }

        .link-icon {
            font-size: 16px;
        }

        /* Responsive */
        @media (max-width: 1200px) {
            .timeline {
                overflow-x: auto;
                padding-bottom: 20px;
            }
            
            .phase-card {
                min-width: 180px;
            }
            
            .current-grid {
                grid-template-columns: 1fr;
            }
            
            .archive-container {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 768px) {
            .main { padding: 20px; }
            .vision-pillars { grid-template-columns: 1fr; }
            .link-list { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>

<header class="header">
    <div class="header-content">
        <div class="logo">Open<span>Claw</span> Strategic Cockpit</div>
        <div class="last-updated">Updated: 2026-03-30</div>
    </div>
</header>

<main class="main">

    <!-- 1. THE VISION -->
    <section id="vision">
        <div class="section-title">The Vision</div>
        
        <div class="vision-card">
            <h1 class="vision-title">Building a Reliable, Autonomous Trading Infrastructure</h1>
            
            <div class="vision-description">
                <p>OpenClaw is a systematic trading infrastructure designed to operate with minimal human intervention while maintaining rigorous safety standards. The long-term goal is a fully autonomous system that can detect opportunities, execute trades, manage risk, and maintain operational continuity without requiring constant oversight.</p>
                
                <p>By Phase 9, OpenClaw will demonstrate production-ready reliability through 48+ hours of continuous validated runtime, comprehensive safety systems, and battle-tested operational procedures.</p>
            </div>
            
            <div class="vision-pillars">
                <div class="pillar">
                    <div class="pillar-number">01</div>
                    <div class="pillar-title">Reliability First</div>
                    <div class="pillar-text">Every component designed for fault tolerance and graceful degradation</div>
                </div>
                <div class="pillar">
                    <div class="pillar-number">02</div>
                    <div class="pillar-title">Safety by Design</div>
                    <div class="pillar-text">Multiple independent safety layers prevent catastrophic failures</div>
                </div>
                <div class="pillar">
                    <div class="pillar-number">03</div>
                    <div class="pillar-title">Operational Excellence</div>
                    <div class="pillar-text">Clear procedures, monitoring, and recovery mechanisms for every scenario</div>
                </div>
            </div>
        </div>
    </section>

    <!-- 2. THE TIMELINE -->
    <section id="timeline">
        <div class="section-title">The Timeline</div>
        
        <div class="timeline-container">
            <div class="timeline-header">
                <h2 class="timeline-title">Project Roadmap: Phase 0 → Phase 9</h2>
                <div class="timeline-legend">
                    <div class="legend-item">
                        <div class="legend-dot complete"></div>
                        <span>Complete</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-dot active"></div>
                        <span>Active</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-dot planned"></div>
                        <span>Planned</span>
                    </div>
                </div>
            </div>
            
            <div class="timeline">
                <div class="phase-card complete">
                    <div class="phase-indicator">0</div>
                    <div class="phase-name">Freeze & Archive</div>
                    <div class="phase-description">Legacy system archived and documented</div>
                    <span class="phase-status complete">✓ Complete</span>
                </div>
                
                <div class="phase-card complete">
                    <div class="phase-indicator">1</div>
                    <div class="phase-name">Skeleton & ADRs</div>
                    <div class="phase-description">Architecture decisions documented</div>
                    <span class="phase-status complete">✓ Complete</span>
                </div>
                
                <div class="phase-card complete">
                    <div class="phase-indicator">2</div>
                    <div class="phase-name">Core Reliability</div>
                    <div class="phase-description">Event Store, State Projection, Risk Engine</div>
                    <span class="phase-status complete">✓ Complete</span>
                </div>
                
                <div class="phase-card complete">
                    <div class="phase-indicator">3</div>
                    <div class="phase-name">Observability</div>
                    <div class="phase-description">Logging, Health Monitoring, Reporting</div>
                    <span class="phase-status complete">✓ Complete</span>
                </div>
                
                <div class="phase-card complete">
                    <div class="phase-indicator">4</div>
                    <div class="phase-name">System Boundaries</div>
                    <div class="phase-description">SAFETY/OBSERVABILITY separation defined</div>
                    <span class="phase-status complete">✓ Complete</span>
                </div>
                
                <div class="phase-card active">
                    <div class="phase-indicator">5</div>
                    <div class="phase-name">Operations</div>
                    <div class="phase-description">Runtime Validation, Systemd, Deployment</div>
                    <span class="phase-status active">● Active</span>
                </div>
                
                <div class="phase-card blocked">
                    <div class="phase-indicator">6</div>
                    <div class="phase-name">Test Strategy</div>
                    <div class="phase-description">Integration testing, scenario coverage</div>
                    <span class="phase-status planned">Blocked by P5</span>
                </div>
                
                <div class="phase-card blocked">
                    <div class="phase-indicator">7</div>
                    <div class="phase-name">Strategy Lab ⭐</div>
                    <div class="phase-description">Trading algorithms and signal generation</div>
                    <span class="phase-status planned">Blocked by P6</span>
                </div>
                
                <div class="phase-card blocked">
                    <div class="phase-indicator">8</div>
                    <div class="phase-name">Economics</div>
                    <div class="phase-description">Market analysis and profitability modeling</div>
                    <span class="phase-status planned">Blocked by P7</span>
                </div>
                
                <div class="phase-card blocked">
                    <div class="phase-indicator">9</div>
                    <div class="phase-name">Review & Gate</div>
                    <div class="phase-description">Final validation and production approval</div>
                    <span class="phase-status planned">Blocked by P8</span>
                </div>
            </div>
            
            <div class="dependency-note">
                <strong>Phase 5 blocks all subsequent phases.</strong> The current 48h Runtime Validation (Block 5.0) must succeed before work can begin on Phases 6–9. Phase 7 (Strategy Lab) is the critical path to first live trading.
            </div>
        </div>
    </section>

    <!-- 3. CURRENT STATUS -->
    <section id="current">
        <div class="section-title">Current Status</div>
        
        <div class="current-grid">
            <div class="current-main">
                <div class="current-header">
                    <div>
                        <div class="current-badge">Phase 5.0 Active</div>
                        <h2 class="current-title">Runtime Validation — Re-Run Required</h2>
                        <p class="current-subtitle">The initial 48h validation run concluded with NO-GO status. Fixes have been implemented; a new run is ready to begin.</p>
                    </div>
                </div>
                
                <div class="workstream-list">
                    <div class="workstream-item blocked">
                        <div class="workstream-icon blocked">⏸</div>
                        <div class="workstream-content">
                            <div class="workstream-name">Block 5.0a: Runtime Validation Re-Run</div>
                            <div class="workstream-desc">Fixes for memory growth detection and event store persistence complete. Awaiting 48h validation run to confirm GO status.</div>
                        </div>
                    </div>
                    
                    <div class="workstream-item waiting">
                        <div class="workstream-icon waiting">⏳</div>
                        <div class="workstream-content">
                            <div class="workstream-name">Blocks 5.1–5.4: Operations</div>
                            <div class="workstream-desc">Systemd integration, Control API, Log rotation, and Deployment automation ready to proceed after 5.0 GO.</div>
                        </div>
                    </div>
                    
                    <div class="workstream-item ready">
                        <div class="workstream-icon ready">✓</div>
                        <div class="workstream-content">
                            <div class="workstream-name">Phase 7: Strategy Lab MVP</div>
                            <div class="workstream-desc">Core signal generation and backtesting framework complete. Waiting for operational infrastructure (Phases 5–6).</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="current-sidebar">
                <div class="sidebar-card">
                    <div class="sidebar-title">Project Progress</div>
                    <div class="sidebar-value">48%</div>
                    <div class="sidebar-label">4 of 9 phases complete</div>
                </div>
                
                <div class="sidebar-card">
                    <div class="sidebar-title">Test Coverage</div>
                    <div class="sidebar-value">191</div>
                    <div class="sidebar-label">tests passing</div>
                </div>
                
                <div class="sidebar-card">
                    <div class="sidebar-title">Last Milestone</div>
                    <div class="sidebar-value" style="font-size: 18px;">Phase 4 Complete</div>
                    <div class="sidebar-label">System Boundaries frozen</div>
                </div>
            </div>
        </div>
    </section>

    <!-- 4. THE ARCHIVE -->
    <section id="archive">
        <div class="section-title">The Archive</div>
        
        <div class="archive-container">
            <div class="archive-card success">
                <div class="archive-date">March 2026</div>
                <div class="archive-title">Phase 4 Completed — Code Freeze Achieved</div>
                <div class="archive-desc">Successfully froze the codebase after 191 passing tests. The SAFETY/OBSERVABILITY boundary architecture was validated and documented.</div>
                <span class="archive-tag success">✓ Milestone</span>
            </div>
            
            <div class="archive-card learning">
                <div class="archive-date">March 2026</div>
                <div class="archive-title">Phase 5.0 Runtime Validation — Learning</div>
                <div class="archive-desc">The initial 48h run revealed that in-memory event storage causes false-positive memory alerts. This led to critical fixes: persistent event store requirement and improved trend detection.</div>
                <span class="archive-tag learning">⚡ Learning</span>
            </div>
            
            <div class="archive-card success">
                <div class="archive-date">February–March 2026</div>
                <div class="archive-title">Core Architecture Validated</div>
                <div class="archive-desc">Event Store, State Projection, Risk Engine, and Reconcile modules completed with comprehensive test coverage. All SAFETY-critical paths covered.</div>
                <span class="archive-tag success">✓ Milestone</span>
            </div>
            
            <div class="archive-card learning">
                <div class="archive-date">February 2026</div>
                <div class="archive-title">Legacy System Archived</div>
                <div class="archive-desc">Previous iteration archived after learning that runtime validation must be designed in from the start, not retrofitted.</div>
                <span class="archive-tag learning">📚 Foundation</span>
            </div>
        </div>
    </section>

    <!-- 5. DEEP DIVE -->
    <section id="deep-dive">
        <div class="section-title">Deep Dive</div>
        
        <div class="deep-dive" id="deepDivePanel">
            <div class="deep-dive-header" onclick="document.getElementById('deepDivePanel').classList.toggle('expanded')">
                <div class="deep-dive-title">Technical Details, Acceptance Criteria & Documentation</div>
                <div class="deep-dive-toggle">▼</div>
            </div>
            
            <div class="deep-dive-body">
                
                <div class="detail-section">
                    <div class="detail-section-title">Phase 5.0 Runtime Validation Criteria</div>
                    <table class="detail-table">
                        <thead>
                            <tr>
                                <th>Criterion</th>
                                <th>Initial Run</th>
                                <th>Target</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>Duration</td>
                                <td>48h ✓</td>
                                <td>48h</td>
                                <td><span class="status-badge pass">PASS</span></td>
                            </tr>
                            <tr>
                                <td>Heartbeat Completeness</td>
                                <td>100% ✓</td>
                                <td>≥95%</td>
                                <td><span class="status-badge pass">PASS</span></td>
                            </tr>
                            <tr>
                                <td>Health Check Success</td>
                                <td>0% ✗</td>
                                <td>≥95%</td>
                                <td><span class="status-badge fail">FAIL</span></td>
                            </tr>
                            <tr>
                                <td>Memory Growth</td>
                                <td>25% ✗</td>
                                <td>&lt;10%</td>
                                <td><span class="status-badge fail">FAIL</span></td>
                            </tr>
                            <tr>
                                <td>No Gaps &gt;5min</td>
                                <td>0 ✓</td>
                                <td>0</td>
                                <td><span class="status-badge pass">PASS</span></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="detail-section">
                    <div class="detail-section-title">Fixes Implemented (5.0a)</div>
                    <table class="detail-table">
                        <thead>
                            <tr>
                                <th>Priority</th>
                                <th>Fix</th>
                                <th>Impact</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>P0</td>
                                <td>EVENT_STORE_PATH mandatory</td>
                                <td>Eliminates in-memory false positives</td>
                            </tr>
                            <tr>
                                <td>P1</td>
                                <td>Memory trend algorithm (6h window)</td>
                                <td>Filters GC oscillations from growth calculation</td>
                            </tr>
                            <tr>
                                <td>P2</td>
                                <td>Health check tracking fix</td>
                                <td>Accurate pass/fail rate reporting</td>
                            </tr>
                            <tr>
                                <td>P3</td>
                                <td>Remove in-memory fallback</td>
                                <td>Hard fail if persistence unavailable</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="detail-section">
                    <div class="detail-section-title">Documentation & Resources</div>
                    <div class="link-list">
                        <a href="architecture/" class="link-item">
                            <span class="link-icon">📐</span>
                            <span>Architecture (ADRs)</span>
                        </a>
                        <a href="runbooks/" class="link-item">
                            <span class="link-icon">📋</span>
                            <span>Runbooks</span>
                        </a>
                        <a href="test-reports.md" class="link-item">
                            <span class="link-icon">📊</span>
                            <span>Test Reports</span>
                        </a>
                        <a href="economics.md" class="link-item">
                            <span class="link-icon">💰</span>
                            <span>Economics</span>
                        </a>
                        <a href="strategy-lab/" class="link-item">
                            <span class="link-icon">🧪</span>
                            <span>Strategy Lab</span>
                        </a>
                        <a href="changelog.md" class="link-item">
                            <span class="link-icon">📝</span>
                            <span>Changelog</span>
                        </a>
                    </div>
                </div>
                
            </div>
        </div>
    </section>

</main>

<script>
    // Auto-expand on first visit (optional)
    if (!localStorage.getItem('hasVisited')) {
        localStorage.setItem('hasVisited', 'true');
    }
</script>

</body>
</html>