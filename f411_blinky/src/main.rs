#![no_std]
#![no_main]

use panic_halt as _;

use core::fmt::Write;
use cortex_m_rt::entry;

use stm32f4xx_hal::{pac, prelude::*, rcc::Config, serial::config::Config as SerialConfig};

#[entry]
fn main() -> ! {
    // STM32 peripheral 가져오기
    let dp = pac::Peripherals::take().unwrap();

    // Cortex-M core peripheral 가져오기
    let cp = cortex_m::peripheral::Peripherals::take().unwrap();

    // HSI → SYSCLK 48 MHz
    let mut rcc = dp.RCC.freeze(Config::hsi().sysclk(48.MHz()));

    // GPIOA 초기화
    let gpioa = dp.GPIOA.split(&mut rcc);

    // NUCLEO-F411RE LD2 = PA5
    let mut led = gpioa.pa5.into_push_pull_output();

    // USART2 PA2(TX)/PA3(RX): ST-LINK virtual COM port, 115200 8N1.
    let mut serial = dp
        .USART2
        .serial(
            (gpioa.pa2, gpioa.pa3),
            SerialConfig::default().baudrate(115_200.bps()),
            &mut rcc,
        )
        .unwrap();

    // Emit one boot banner for the Agentic HIL UART assertion.
    serial.write_str("Hello World\r\n").unwrap();

    // Cortex-M SysTick을 delay timer로 사용
    let mut delay = cp.SYST.delay(&rcc.clocks);

    loop {
        led.toggle();

        delay.delay_ms(1000);
    }
}
