//! NUCLEO-F411RE LD2 heartbeat using the internal HSI clock and PA5.
//!
//! `SysTick` delays provide a simple demo clock, not a precise wall clock.

#![no_std]
#![no_main]

use app_logic::Blinker;
use cortex_m_rt::entry;
use panic_halt as _;
use stm32f4xx_hal::{pac, prelude::*, rcc::Config};

#[entry]
fn main() -> ! {
    let device = pac::Peripherals::take().unwrap_or_else(|| halt());
    let core = cortex_m::Peripherals::take().unwrap_or_else(|| halt());

    // HSI avoids relying on an external oscillator or ST-LINK MCO wiring.
    let mut rcc = device.RCC.freeze(Config::hsi());
    let gpioa = device.GPIOA.split(&mut rcc);
    let mut led = gpioa.pa5.into_push_pull_output();
    let mut delay = core.SYST.delay(&rcc.clocks);
    let mut blinker = Blinker::new(0);
    let mut now_ms = 0_u32;
    led.set_low();

    loop {
        delay.delay_ms(1_u32);
        now_ms = now_ms.wrapping_add(1);
        if blinker.update(now_ms) {
            led.set_high();
        } else {
            led.set_low();
        }
    }
}

fn halt() -> ! {
    loop {
        cortex_m::asm::wfi();
    }
}
