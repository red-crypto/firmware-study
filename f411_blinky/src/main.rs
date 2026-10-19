#![no_std]
#![no_main]

use panic_halt as _;

use cortex_m_rt::entry;

use stm32f4xx_hal::{
    pac,
    prelude::*,
    rcc::Config,
};

#[entry]
fn main() -> ! {
    // STM32 peripheral 가져오기
    let dp = pac::Peripherals::take().unwrap();

    // Cortex-M core peripheral 가져오기
    let cp = cortex_m::peripheral::Peripherals::take().unwrap();

    // HSI → SYSCLK 48 MHz
    let mut rcc =
        dp.RCC.freeze(Config::hsi().sysclk(48.MHz()));

    // GPIOA 초기화
    let gpioa = dp.GPIOA.split(&mut rcc);

    // NUCLEO-F446RE LD2 = PA5
    let mut led =
        gpioa.pa5.into_push_pull_output();

    // Cortex-M SysTick을 delay timer로 사용
    let mut delay =
        cp.SYST.delay(&rcc.clocks);

    loop {
        led.toggle();

        delay.delay_ms(1000);
    }
}