import Foundation
import ApplicationServices
import AppKit
import Swindler
import PromiseKit

// MARK: - Debug logging

struct Logger {
	static let isDebugEnabled: Bool = {
		let args = CommandLine.arguments
		return args.contains("-d") || args.contains("--debug")
	}()

	static func debug(_ message: @autoclosure () -> String) {
		guard isDebugEnabled else { return }
		print("[DEBUG] \(message())")
	}

	static func info(_ message: @autoclosure () -> String) {
		print(message())
	}

	static func warn(_ message: @autoclosure () -> String) {
		print("[WARN] \(message())")
	}
}

// MARK: - Accessibility permission

@discardableResult
func ensureAccessibilityPermission(prompt: Bool) -> Bool {
	// Use string key to avoid concurrency warnings on CFString global
	let options: CFDictionary = ["kAXTrustedCheckOptionPrompt": prompt] as CFDictionary
	let trusted = AXIsProcessTrustedWithOptions(options)
	if !trusted {
		Logger.warn("Accessibility permission not granted yet. Grant access in System Settings › Privacy & Security › Accessibility, then re-run.")
	}
	return trusted
}

// MARK: - Models & helpers

private let simulatorBundleId = "com.apple.iphonesimulator"
private let terminalBundleIds: Set<String> = [
	"com.apple.Terminal",
	"com.googlecode.iterm2"
]

func clampPointWithinScreen(frame: CGRect, desiredOrigin: CGPoint, screen: NSScreen) -> CGPoint {
	let screenFrame = screen.visibleFrame
	let clampedX = max(screenFrame.minX, min(desiredOrigin.x, screenFrame.maxX - frame.width))
	let clampedY = max(screenFrame.minY, min(desiredOrigin.y, screenFrame.maxY - frame.height))
	return CGPoint(x: clampedX, y: clampedY)
}

func screenForFrame(_ frame: CGRect) -> NSScreen? {
	return NSScreen.screens.first { $0.frame.intersects(frame) }
}

// Attempts to match a terminal window to the launching process by walking the parent PID.
// If that fails, falls back to frontmost/most-recent terminal window.
func selectTerminalWindow(state: Swindler.State) -> Window? {
	// Prefer windows from known terminal apps
	let terminalWindows: [Window] = state.knownWindows.filter { window in
		if let bundleId = window.application.bundleIdentifier {
			return terminalBundleIds.contains(bundleId)
		}
		return false
	}.sorted(by: { (lhs: Window, rhs: Window) -> Bool in
		let la = lhs.frame.value.size.width * lhs.frame.value.size.height
		let ra = rhs.frame.value.size.width * rhs.frame.value.size.height
		return la > ra
	})

	guard !terminalWindows.isEmpty else { return nil }

	let parentPid = getppid()
	Logger.debug("Parent PID: \(parentPid)")

	// Try to pick a window whose owning app matches parent or its ancestry (best-effort)
	if let matchByPid = terminalWindows.first(where: { $0.application.processIdentifier == parentPid }) {
		Logger.debug("Matched terminal by parent PID: \(String(describing: matchByPid.title.value))")
		return matchByPid
	}

	// Fallback: choose focused or frontmost terminal window
	Logger.debug("Using first terminal window: \(terminalWindows.first?.title.value ?? "<untitled>")")
	return terminalWindows.first
}

func selectSimulatorWindow(state: Swindler.State) -> Window? {
	let simulatorWindows: [Window] = state.knownWindows.filter { $0.application.bundleIdentifier == simulatorBundleId }
	// Prefer largest window by area
	let sorted = simulatorWindows.sorted(by: { (lhs: Window, rhs: Window) -> Bool in
		let la = lhs.frame.value.size.width * lhs.frame.value.size.height
		let ra = rhs.frame.value.size.width * rhs.frame.value.size.height
		return la > ra
	})
	return sorted.first
}

// Align terminal underneath simulator with a margin, respecting screen bounds.
func alignTerminal(under simulator: Window, terminal: Window, margin: CGFloat) {
	let simulatorFrame = simulator.frame.value
	let terminalFrame = terminal.frame.value

	// Match terminal width to simulator's width; cap terminal height to 250.
	let newTerminalSize = CGSize(
		width: simulatorFrame.size.width,
		height: min(terminalFrame.size.height, 250)
	)

	let desiredOrigin = CGPoint(
		x: simulatorFrame.origin.x,
		y: simulatorFrame.origin.y - newTerminalSize.height - margin
	)

	let screen = screenForFrame(simulatorFrame) ?? NSScreen.main
	let clampedOrigin: CGPoint
	if let screen {
		let targetFrameForClamp = CGRect(origin: .zero, size: newTerminalSize)
		clampedOrigin = clampPointWithinScreen(frame: targetFrameForClamp, desiredOrigin: desiredOrigin, screen: screen)
	} else {
		clampedOrigin = desiredOrigin
	}

	Logger.debug("Aligning terminal to x=\(clampedOrigin.x), y=\(clampedOrigin.y), size=\(NSStringFromSize(newTerminalSize)) below simulator frame=\(NSStringFromRect(simulatorFrame))")
	_ = terminal.frame.set(CGRect(origin: clampedOrigin, size: newTerminalSize))
}

// MARK: - Event wiring

final class AlignmentController {
	private let state: Swindler.State
	private var simulatorWindow: Window?
	private var terminalWindow: Window?
	private let margin: CGFloat
	private var activationObserver: Any?
	private var lastSimulatorActivationAt: Date?


	init(state: Swindler.State, margin: CGFloat) {
		self.state = state
		self.margin = margin
	}

	func start() {
		refreshWindows(reason: "initial")
		subscribeToState()
		subscribeToAppActivation()
	}

	private func refreshWindows(reason: String) {
		let newSim = selectSimulatorWindow(state: state)
		let newTerm = selectTerminalWindow(state: state)
		if newSim == nil { Logger.warn("Simulator window not found (\(reason)).") }
		if newTerm == nil { Logger.warn("Terminal window not found (\(reason)).") }
		simulatorWindow = newSim
		terminalWindow = newTerm
		if let sim = simulatorWindow, let term = terminalWindow {
			Logger.debug("Selected simulator: \(sim.title.value) | terminal: \(term.title.value)")
			alignTerminal(under: sim, terminal: term, margin: margin)
		}
	}

	private func subscribeToState() {
		// Listen for new windows / destroyed windows to refresh selection.
		state.on { (event: WindowCreatedEvent) in
			Logger.debug("WindowCreated: app=\(event.window.application.bundleIdentifier ?? "?") title=\(event.window.title.value)")
			self.refreshWindows(reason: "window created")
		}
		state.on { (event: WindowDestroyedEvent) in
			Logger.debug("WindowDestroyed: app=\(event.window.application.bundleIdentifier ?? "?") title=\(event.window.title.value)")
			self.refreshWindows(reason: "window destroyed")
		}
		state.on { (event: ApplicationLaunchedEvent) in
			Logger.debug("AppLaunched: \(event.application.bundleIdentifier ?? "?")")
			self.refreshWindows(reason: "app launched")
		}
		state.on { (event: ApplicationTerminatedEvent) in
			Logger.debug("AppTerminated: \(event.application.bundleIdentifier ?? "?")")
			self.refreshWindows(reason: "app terminated")
		}
		state.on { (event: WindowFrameChangedEvent) in
			guard let sim = self.simulatorWindow, let term = self.terminalWindow else { return }
			if event.window == sim {
				Logger.debug("Simulator WindowFrameChangedEvent -> realign")
				self.align(sim: sim, term: term)
			}
		}
	}

	private func subscribeToAppActivation() {
		activationObserver = NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main) { [weak self] notif in
			Logger.debug("NSWorkspace.didActivateApplicationNotification: \(notif)")
			guard let self else { return }
			guard let app = notif.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication else { return }
			if app.bundleIdentifier == simulatorBundleId {
				// Debounce: if we just handled activation very recently, skip
				let now = Date()
				if let last = self.lastSimulatorActivationAt, now.timeIntervalSince(last) < 0.10 {
					Logger.debug("Debounced simulator activation (<10ms)")
					return
				}
				self.lastSimulatorActivationAt = now

				// Refresh selection, then briefly activate terminal and immediately reactivate Simulator
				self.refreshWindows(reason: "simulator activated")
				if let term = self.terminalWindow,
					let termApp = NSRunningApplication(processIdentifier: term.application.processIdentifier) {
					Logger.debug("Activating terminal, then Simulator (debounced)")
					termApp.activate(options: [.activateIgnoringOtherApps])
					app.activate(options: [.activateIgnoringOtherApps])
				}
			}
		}
	}

	private func align(sim: Window, term: Window) {
		alignTerminal(under: sim, terminal: term, margin: margin)
	}
}

// MARK: - Entry point

@main
struct AlignerMain {
	static func main() {
		let margin: CGFloat = 12

		guard ensureAccessibilityPermission(prompt: true) else {
			exit(1)
		}

		firstly {
			Swindler.initialize()
		}.done { state in
			Logger.debug("Swindler initialized. Apps=\(state.runningApplications.count) windows=\(state.knownWindows.count)")
			let controller = AlignmentController(state: state, margin: margin)
			controller.start()
		}.catch { error in
			Logger.warn("Failed to initialize Swindler: \(error)")
			exit(1)
		}

		RunLoop.main.run()
	}
}
