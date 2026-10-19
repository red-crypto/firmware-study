//! Hardware-independent LED scheduling for the NUCLEO-F411RE example.
//!
//! Time and GPIO access belong to the board layer. This crate accepts a clock
//! reading and returns the requested LED state, so its behavior can be tested
//! on a development computer without a connected board.

#![no_std]
#![forbid(unsafe_code)]

/// Time between LED transitions, in milliseconds.
pub const INTERVAL_MS: u32 = 500;

/// An initially off LED that changes state every [`INTERVAL_MS`] milliseconds.
///
/// Feed this scheduler readings from a monotonically advancing millisecond
/// clock. The clock may wrap from [`u32::MAX`] to zero. The elapsed time since
/// the last scheduled transition must remain below one complete `u32` clock
/// period; larger gaps and backward clock adjustments cannot be distinguished
/// from normal wrapping.
#[derive(Debug)]
pub struct Blinker {
    last_transition_ms: u32,
    led_on: bool,
}

impl Blinker {
    /// Starts with the LED off and schedules its first transition after
    /// [`INTERVAL_MS`] milliseconds have elapsed from `now_ms`.
    #[must_use]
    pub const fn new(now_ms: u32) -> Self {
        Self {
            last_transition_ms: now_ms,
            led_on: false,
        }
    }

    /// Returns the requested LED state without advancing the scheduler.
    #[must_use]
    pub const fn state(&self) -> bool {
        self.led_on
    }

    /// Advances the scheduler and returns the requested LED state.
    ///
    /// Missed intervals are accounted for together: an odd number changes the
    /// state and an even number leaves it unchanged. Transition times retain
    /// their original phase even when calls arrive late.
    ///
    /// `now_ms` must follow the wrapping clock contract documented on
    /// [`Blinker`].
    pub fn update(&mut self, now_ms: u32) -> bool {
        let elapsed_ms = now_ms.wrapping_sub(self.last_transition_ms);
        let intervals = elapsed_ms / INTERVAL_MS;

        if intervals > 0 {
            if intervals % 2 == 1 {
                self.led_on = !self.led_on;
            }
            self.last_transition_ms = self
                .last_transition_ms
                .wrapping_add(intervals * INTERVAL_MS);
        }

        self.led_on
    }
}

#[cfg(test)]
mod tests {
    use super::Blinker;

    #[test]
    fn starts_off_at_the_supplied_clock_reading() {
        let mut blinker = Blinker::new(42);

        assert!(!blinker.state());
        assert!(!blinker.update(42));
    }

    #[test]
    fn changes_state_only_when_the_first_interval_is_complete() {
        let mut blinker = Blinker::new(100);

        assert!(!blinker.update(599));
        assert!(blinker.update(600));
        assert!(blinker.state());
    }

    #[test]
    fn repeated_clock_readings_do_not_add_transitions() {
        let mut blinker = Blinker::new(0);

        assert!(blinker.update(500));
        assert!(blinker.update(500));
        assert!(blinker.update(500));
        assert!(!blinker.update(1_000));
        assert!(!blinker.update(1_000));
    }

    #[test]
    fn an_even_number_of_missed_intervals_preserves_the_state() {
        let mut blinker = Blinker::new(0);

        assert!(!blinker.update(2_000));
        assert!(blinker.update(2_500));
        assert!(blinker.update(4_500));
    }

    #[test]
    fn an_odd_number_of_missed_intervals_changes_the_state() {
        let mut blinker = Blinker::new(0);

        assert!(blinker.update(1_500));
        assert!(!blinker.update(3_000));
    }

    #[test]
    fn late_updates_preserve_the_original_transition_times() {
        let mut blinker = Blinker::new(0);

        assert!(blinker.update(750));
        assert!(blinker.update(999));
        assert!(!blinker.update(1_000));
        assert!(!blinker.update(1_499));
        assert!(blinker.update(1_500));
    }

    #[test]
    fn clock_wrap_preserves_the_first_transition_boundary() {
        let started_at = u32::MAX - 249;
        let mut blinker = Blinker::new(started_at);

        assert!(!blinker.update(started_at.wrapping_add(499)));
        assert!(blinker.update(started_at.wrapping_add(500)));
        assert!(!blinker.update(started_at.wrapping_add(1_000)));
    }

    #[test]
    fn missed_intervals_across_clock_wrap_retain_their_phase() {
        let started_at = u32::MAX - 124;
        let mut blinker = Blinker::new(started_at);

        assert!(blinker.update(started_at.wrapping_add(1_750)));
        assert!(blinker.update(started_at.wrapping_add(1_999)));
        assert!(!blinker.update(started_at.wrapping_add(2_000)));
    }
}
