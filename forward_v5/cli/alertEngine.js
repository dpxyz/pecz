/**
 * OpenClaw Forward v5 - Alert Engine v1.0
 * Block 5.3.3: Alert Integration
 * 
 * Principles:
 * - Per-source isolation (${rule.name}:${source})
 * - Clean Discord payloads (content vs embeds)
 * - One-shot alerts (no reminders in v1)
 * - Engine-based grace period
 */

class AlertEngine {
  constructor(config = {}) {
    // Grace based on ENGINE start (not service uptime)
    this.engineStartedAt = Date.now();
    this.gracePeriodMs = 120000;
    this.recoveryDelayMs = 5000;
    
    // State stores keyed by ${ruleName}:${source}
    this.cooldowns = new Map();
    this.failures = new Map();
    this.activeAlerts = new Map();
    this.pendingRecoveries = new Map();
    
    this.previousStatus = null;
    this.discordWebhook = config.discordWebhook || process.env.DISCORD_WEBHOOK_URL;
    
    // Fixed v1 rules
    this.rules = [
      {
        name: 'service_down',
        condition: (d) => d.status === 'DOWN',
        severity: 'CRITICAL',
        cooldown: 300000,
        immediate: true
      },
      {
        name: 'heartbeat_stale',
        condition: (d) => d.checks?.heartbeat?.startsWith('STALE'),
        severity: 'WARNING',
        cooldown: 120000,
        immediate: false
      },
      {
        name: 'memory_critical',
        condition: (d) => d.checks?.memory?.startsWith('CRITICAL'),
        severity: 'CRITICAL',
        cooldown: 60000,
        immediate: false
      },
      {
        name: 'circuit_breaker_tripped',
        condition: (d) => d.checks?.circuit_breaker === 'OPEN',
        severity: 'WARNING',
        cooldown: 300000,
        immediate: false
      }
    ];
  }
  
  evaluate(healthData) {
    const now = Date.now();
    const source = healthData.component || 'unknown';
    
    const engineUptime = now - this.engineStartedAt;
    if (engineUptime < this.gracePeriodMs) {
      return {
        fired: [],
        active: this.getActiveAlerts(),
        inGrace: true,
        graceRemaining: this.gracePeriodMs - engineUptime
      };
    }
    
    const firedAlerts = [];
    const statusChangedToDown = this.previousStatus === 'UP' && healthData.status === 'DOWN';
    this.previousStatus = healthData.status;
    
    for (const rule of this.rules) {
      const stateKey = `${rule.name}:${source}`;
      const triggered = rule.condition(healthData);
      const failures = this.failures.get(stateKey) || 0;
      const isActive = this.activeAlerts.has(stateKey);
      const lastFire = this.cooldowns.get(stateKey);
      const cooldownActive = lastFire && (now - lastFire) < rule.cooldown;
      
      if (triggered) {
        this.failures.set(stateKey, failures + 1);
      } else {
        this.failures.set(stateKey, 0);
      }
      
      let shouldFire = false;
      if (rule.immediate && statusChangedToDown) {
        shouldFire = !cooldownActive;
      } else if (triggered) {
        shouldFire = (failures + 1) >= 2 && !cooldownActive;
      }
      
      if (shouldFire && !isActive) {
        const alert = this.createAlert(rule, healthData, now);
        this.activeAlerts.set(stateKey, alert);
        this.cooldowns.set(stateKey, now);
        firedAlerts.push(alert);
        
        if (this.pendingRecoveries.has(stateKey)) {
          clearTimeout(this.pendingRecoveries.get(stateKey));
          this.pendingRecoveries.delete(stateKey);
        }
      }
      
      if (!triggered && isActive && !this.pendingRecoveries.has(stateKey)) {
        const timeoutId = setTimeout(() => {
          this.activeAlerts.delete(stateKey);
          this.pendingRecoveries.delete(stateKey);
        }, this.recoveryDelayMs);
        this.pendingRecoveries.set(stateKey, timeoutId);
      }
    }
    
    return {
      fired: firedAlerts,
      active: this.getActiveAlerts(),
      inGrace: false,
      graceRemaining: 0
    };
  }
  
  createAlert(rule, data, timestamp) {
    const message = this.buildMessage(rule, data);
    
    return {
      id: `${rule.name}_${data.component || 'unknown'}_${timestamp}`,
      rule: rule.name,
      severity: rule.severity,
      message,
      timestamp: new Date(timestamp).toISOString(),
      source: data.component || 'unknown',
      metadata: { status: data.status, reason: data.reason, checks: data.checks },
      dashboard: {
        show: true,
        color: rule.severity === 'CRITICAL' ? 'red' : 'yellow',
        icon: rule.severity === 'CRITICAL' ? '🔴' : '🟡'
      },
      discord: rule.severity !== 'INFO'
    };
  }
  
  buildMessage(rule, data) {
    switch (rule.name) {
      case 'service_down':
        return `Service readiness failed: ${data.reason || 'unknown'}`;
      case 'heartbeat_stale': {
        const match = data.checks?.heartbeat?.match(/STALE \((\d+)/);
        return `No heartbeat for ${match ? match[1] + 's' : '60s+'}`;
      }
      case 'memory_critical': {
        const match = data.checks?.memory?.match(/CRITICAL \((\d+)%/);
        return `Memory critical: ${match ? match[1] + '%' : '95%+'}`;
      }
      case 'circuit_breaker_tripped':
        return 'Risk protection triggered - execution halted';
      default:
        return `${rule.name} triggered`;
    }
  }
  
  shouldSendDiscord(alert) {
    return alert.severity === 'CRITICAL' || alert.severity === 'WARNING';
  }
  
  buildDiscordPayload(alert) {
    if (alert.severity === 'CRITICAL') {
      return {
        content: '@here 🚨 CRITICAL Alert',
        embeds: [{
          title: 'FORWARD V5: CRITICAL',
          description: alert.message,
          color: 16711680,
          timestamp: alert.timestamp,
          footer: { text: `Rule: ${alert.rule}` }
        }],
        allowed_mentions: { parse: ['everyone'] }
      };
    }
    
    if (alert.severity === 'WARNING') {
      return {
        content: null,
        embeds: [{
          title: 'FORWARD V5: WARNING',
          description: alert.message,
          color: 16776960,
          timestamp: alert.timestamp,
          footer: { text: `Rule: ${alert.rule}` }
        }],
        allowed_mentions: { parse: [] }
      };
    }
    
    return null;
  }
  
  async sendDiscord(alert) {
    if (!this.shouldSendDiscord(alert)) return;
    if (!this.discordWebhook) return;
    
    const payload = this.buildDiscordPayload(alert);
    if (!payload) return;
    
    try {
      await this.postWebhook(this.discordWebhook, payload);
    } catch (err) {
      console.error('Discord webhook failed:', err.message);
    }
  }
  
  postWebhook(url, payload) {
    return new Promise((resolve, reject) => {
      const https = require('https');
      const urlObj = new URL(url);
      const data = JSON.stringify(payload);
      
      const options = {
        hostname: urlObj.hostname,
        port: urlObj.port || 443,
        path: urlObj.pathname + urlObj.search,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      };
      
      const req = https.request(options, (res) => {
        let response = '';
        res.on('data', (chunk) => response += chunk);
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(response);
          } else {
            reject(new Error(`HTTP ${res.statusCode}`));
          }
        });
      });
      
      req.on('error', reject);
      req.write(data);
      req.end();
    });
  }
  
  getActiveAlerts() {
    return Array.from(this.activeAlerts.values());
  }
  
  isInGracePeriod() {
    return (Date.now() - this.engineStartedAt) < this.gracePeriodMs;
  }
}

module.exports = AlertEngine;
