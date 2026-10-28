# Reboot identity verification — 5 lần reboot thật qua USB (A-W02-03)

Ngày: 2026-10-18, board **ESP32-S3 (MAC `e0:72:a1:bc:cf:4c`)** trên COM4, firmware
**ESP-IDF W02 thực sự đã nạp từ artifact CI** (commit `1b93f572` — xem
`flash-provenance.md`).

## Input

* Raw log: `serial-reboot-original.log` (58 271 byte, LF, SHA-256
  `e48977be20cd4e78d233f6c458d05e2d4486930283e0bac17e491320194f7854`, byte-for-byte
  nguyên bản byte-for-byte từ tool thu — không chèn/xoá sửa dòng nào).
* Verifier output: `reboot-verification-report.txt` (
  `2fa3f0ed07b92d400a0b4d22e1a063344fb68e736dc83157a6d03e8f8d39388a`) và
  `reboot-verification.json` (`08dcd97aa88f3be5dc3bc82200eb7dea93f7ecc75425ac5d6cae15eb4815c739`).

## Phương thức reset (host-driven, không cần bấm nút)

Tool `firmware/tools/cg_auto_reboot.py` (commit `1b93f572`) thay người dùng bấm **RST/EN**:

* **Cơ chế đã được thử trên chính board này** — mở cổng rồi hạ cả DTR/RTS，
  peripheral USB-Serial-JTAG biến thành `rst:0x15 (USB_UART_CHIP_RESET)` và
  chip boot từ flash (`boot:0x8 SPI_FAST_FLASH_BOOT`). Độc lập: đúng banner
  `rst:0x15 (USB_UART_CHIP_RESET),boot:0x8 (SPI_FAST_FLASH_BOOT)` xuất hiện **6/6 reset**
  trong log raw.
* Phương án RTS-only kiểu esptool `hard_reset` đã thử trước đó **không reset được app**
  trên S3 native USB-Serial-JTAG (không banner, 0 boot block — chip chạy xuyên suốt) —
  ghi nhận để người sau không lặp lại nhầm.
* Mỗi reset là **một chu kỳ đóng→mở cổng thật**, không lặp log, không suy diễn.

## Kết quả verifier chính thức

`py firmware/tools/cg_verify_reboots.py serial-reboot-original.log --min-boots 5`:

```text
verdict              : IDENTITY_STABLE
boots observed       : 6 (min required 5)
boot ids             : 227e6f67, 50313e8c, c864acea, 222be57b, 99b3dcb5, ae20928d
boot counts (NVS)    : [5, 6, 7, 8, 9, 10]
boot metadata        : OK (boot_id distinct, boot_count increasing)
REBOOT IDENTITY: PASS (6 boots, roles stable, boot metadata consistent)
```

* `boot_count` **liên tục 5…10** qua NVS (không reset bộ đếm) ⇒ 5 lần reboot là boot thật,
  mỗi reboot phải đi kèm một khối `#CG BOOT` riêng (không thể dán lặp một khối).
* `boot_id` (esp_random khởi mỗi boot) **6 giá trị phân biệt** — không khối nào bị lặp.

## ROM→role ở từng boot (tự kiểm từ raw log — gồm cả SPARE)

Software check (script tái lập từ raw log; ngoài phạm vi T1/T2/T3 mà verifier in):

| boot_count | boot_id | T1 | T2 | T3 | SPARE | 4/4 present=1 | khớp bản đồ đóng băng |
|---|---|---|---|---|---|---|---|
| 5 | 227e6f67 | 287088CA00000051 | 28AEBF2200000006 | 28CBE9CA00000072 | 283BE5C9000000A9 | ✔ | ✔ |
| 6 | 50313e8c | 287088CA00000051 | 28AEBF2200000006 | 28CBE9CA00000072 | 283BE5C9000000A9 | ✔ | ✔ |
| 7 | c864acea | 287088CA00000051 | 28AEBF2200000006 | 28CBE9CA00000072 | 283BE5C9000000A9 | ✔ | ✔ |
| 8 | 222be57b | 287088CA00000051 | 28AEBF2200000006 | 28CBE9CA00000072 | 283BE5C9000000A9 | ✔ | ✔ |
| 9 | 99b3dcb5 | 287088CA00000051 | 28AEBF2200000006 | 28CBE9CA00000072 | 283BE5C9000000A9 | ✔ | ✔ |
| 10 | ae20928d | 287088CA00000051 | 28AEBF2200000006 | 28CBE9CA00000072 | 283BE5C9000000A9 | ✔ | ✔ |

`#CG ROMS required_present=3/3 known=4 known_present=4` — **6/6 boots** như nhau.
Không có role nào đổi ROM, không có ROM nào bị dồn vào 2 role (verifier: `mismatches=[]
` = phải để `mismatches: []`).

## Ý nghĩa cho hồ sơ W02

1. **A-W02-03**: yêu cầu ≥5 chu kỳ reboot giữ nguyên ROM→role — **đã có bằng chứng
   thật, host-driven trên chính device đích** → `HARDWARE VERIFIED — 6 BOOT IDENTITY STABLE`.
2. **A-W02-05 (ROM provenance)**: phần "chưa có `#CG ROM` trong raw capture" của phiên
   620 mẫu (sketch standalone) giờ được **bù bằng bằng chứng cùng-boot ở firmware chính**:
   mỗi boot của firmware ESP-IDF đều in đầy đủ 4 ROM + `#CG ROMS`, **từ NVS freezing
   cùng `coldguard_config.h`** — trạng thái ROM chuyển thành
   `ROM IDENTITY VERIFIED ACROSS 6 REAL BOOTS (ESP-IDF)`. Trạng thái sketch-620-sample
   không đổi — vẫn chỉ là consistency check, không dùng để tuyên bố firmware runtime.

## Giới hạn được khai báo trung thực

* `boot_count` bắt đầu thấy ở log là **5** — nghĩa là trước khi capture bắt đầu, board đã
  boot 4 lần trong lúc esptool chip-id/flash-id/read-flash/write-flash (mỗi lần hard-reset
  là một boot thật). Không hề là lỗi; được khai báo để chứng minh NVS **không** được
  reset thủ công.
* Reset #0 trong log (context segment) cũng là một boot thật nhưng chủ ý **không** đem
  vào tập 5 reboot (verifier tự thấy 6).
* Định dạng ROM này **không** đụng đến phần `physical_label` — dán nhãn vật lý vẫn
  `PENDING` (A-W02-02, do người dùng tự làm).
* Thời gian boot giữa 2 chu kỳ có thể lẫn các dòng watchdog/kernel không liên quan tới
  danh tính; chúng được giữ nguyên trong raw log; mọi dòng `#CG` đều theo parser grammar
  v1 (không dòng nào bị cắt hoặc đếm sai).
