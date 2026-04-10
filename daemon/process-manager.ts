/**
 * Claw-ED Daemon — Process Manager
 *
 * Handles PID file management, logging, and service lifecycle
 * for the always-on background daemon.
 */
import { readFileSync, writeFileSync, unlinkSync, existsSync, mkdirSync, createWriteStream, statSync } from 'fs'
import { join } from 'path'
import { homedir } from 'os'
import { execSync, spawn } from 'child_process'

const EDUAGENT_DIR = join(homedir(), '.eduagent')
const PID_FILE = join(EDUAGENT_DIR, 'daemon.pid')
const LOG_FILE = join(EDUAGENT_DIR, 'daemon.log')

export class ProcessManager {
  private logStream: ReturnType<typeof createWriteStream> | null = null

  constructor() {
    if (!existsSync(EDUAGENT_DIR)) {
      mkdirSync(EDUAGENT_DIR, { recursive: true })
    }
  }

  /** Write this process's PID to the PID file. */
  writePid(): void {
    writeFileSync(PID_FILE, String(process.pid), 'utf-8')
    this.log(`Daemon started with PID ${process.pid}`)
  }

  /** Remove the PID file. */
  removePid(): void {
    if (existsSync(PID_FILE)) {
      unlinkSync(PID_FILE)
    }
  }

  /** Read the PID of a running daemon (or null). */
  readPid(): number | null {
    if (!existsSync(PID_FILE)) return null
    try {
      const pid = parseInt(readFileSync(PID_FILE, 'utf-8').trim(), 10)
      if (isNaN(pid)) return null
      // Check if the process is actually running
      try {
        process.kill(pid, 0)
        return pid
      } catch {
        // Process not running, stale PID file
        this.removePid()
        return null
      }
    } catch {
      return null
    }
  }

  /** Check if the daemon is currently running. */
  isRunning(): boolean {
    return this.readPid() !== null
  }

  /** Stop the running daemon by sending SIGTERM. */
  stop(): boolean {
    const pid = this.readPid()
    if (pid === null) {
      console.log('Claw-ED daemon is not running.')
      return false
    }
    try {
      process.kill(pid, 'SIGTERM')
      this.removePid()
      console.log(`Claw-ED daemon stopped (PID ${pid}).`)
      return true
    } catch (err) {
      console.error(`Failed to stop daemon (PID ${pid}):`, err)
      return false
    }
  }

  /** Print daemon status. */
  printStatus(): void {
    const pid = this.readPid()
    if (pid === null) {
      console.log('Claw-ED daemon: stopped')
      return
    }

    // Get process uptime (from PID file mtime)
    let uptime = 'unknown'
    try {
      const pidAge = Date.now() - statSync(PID_FILE).mtimeMs
      const hours = Math.floor(pidAge / 3600000)
      const mins = Math.floor((pidAge % 3600000) / 60000)
      uptime = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
    } catch { /* ignore */ }

    console.log(`Claw-ED daemon: running (PID ${pid}, uptime ${uptime})`)
    console.log(`  Log: ${LOG_FILE}`)
    console.log(`  PID: ${PID_FILE}`)
  }

  /** Tail the daemon log file. */
  tailLogs(follow: boolean = false): void {
    if (!existsSync(LOG_FILE)) {
      console.log('No daemon logs yet.')
      return
    }
    const args = follow ? ['-f', LOG_FILE] : ['-50', LOG_FILE]
    const tail = spawn('tail', args, { stdio: 'inherit' })
    tail.on('close', () => process.exit(0))
  }

  /** Append a log message with timestamp. */
  log(message: string): void {
    const timestamp = new Date().toISOString()
    const line = `[${timestamp}] ${message}\n`

    if (!this.logStream) {
      this.logStream = createWriteStream(LOG_FILE, { flags: 'a' })
    }
    this.logStream.write(line)

    // Also write to stderr in foreground mode
    if (process.env.CLAWED_DAEMON_FOREGROUND === '1') {
      process.stderr.write(line)
    }
  }

  /** Get the log file path. */
  getLogPath(): string {
    return LOG_FILE
  }

  /** Get the PID file path. */
  getPidPath(): string {
    return PID_FILE
  }

  /** Install launchd service (macOS). */
  installLaunchd(daemonPath: string): void {
    const plistDir = join(homedir(), 'Library', 'LaunchAgents')
    const plistPath = join(plistDir, 'com.clawed.daemon.plist')

    if (!existsSync(plistDir)) {
      mkdirSync(plistDir, { recursive: true })
    }

    const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.clawed.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>node</string>
        <string>${daemonPath}</string>
        <string>start</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>
</dict>
</plist>`

    writeFileSync(plistPath, plist, 'utf-8')
    try {
      execSync(`launchctl load "${plistPath}"`)
      console.log(`Launchd service installed: ${plistPath}`)
    } catch (err) {
      console.error('Failed to load launchd service:', err)
    }
  }

  /** Uninstall launchd service (macOS). */
  uninstallLaunchd(): void {
    const plistPath = join(homedir(), 'Library', 'LaunchAgents', 'com.clawed.daemon.plist')
    if (existsSync(plistPath)) {
      try {
        execSync(`launchctl unload "${plistPath}"`)
      } catch { /* may already be unloaded */ }
      unlinkSync(plistPath)
      console.log('Launchd service removed.')
    }
  }

  /** Install systemd user service (Linux). */
  installSystemd(daemonPath: string): void {
    const serviceDir = join(homedir(), '.config', 'systemd', 'user')
    const servicePath = join(serviceDir, 'clawed-daemon.service')

    if (!existsSync(serviceDir)) {
      mkdirSync(serviceDir, { recursive: true })
    }

    const unit = `[Unit]
Description=Claw-ED Teaching Assistant Daemon
After=network.target

[Service]
ExecStart=node "${daemonPath}" start
Restart=always
RestartSec=10
Environment=CLAWED_DAEMON_FOREGROUND=0

[Install]
WantedBy=default.target
`
    writeFileSync(servicePath, unit, 'utf-8')
    try {
      execSync('systemctl --user daemon-reload')
      execSync('systemctl --user enable clawed-daemon')
      execSync('systemctl --user start clawed-daemon')
      console.log(`Systemd service installed: ${servicePath}`)
    } catch (err) {
      console.error('Failed to install systemd service:', err)
    }
  }

  /** Uninstall systemd user service (Linux). */
  uninstallSystemd(): void {
    try {
      execSync('systemctl --user stop clawed-daemon')
      execSync('systemctl --user disable clawed-daemon')
    } catch { /* may not be running */ }
    const servicePath = join(homedir(), '.config', 'systemd', 'user', 'clawed-daemon.service')
    if (existsSync(servicePath)) {
      unlinkSync(servicePath)
      execSync('systemctl --user daemon-reload')
      console.log('Systemd service removed.')
    }
  }
}
