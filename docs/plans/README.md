# Планы задач

История решений и планы реализации. Перед работой сверься с актуальным статусом в git — план мог быть частично или полностью выполнен.

## FSM, закрутка, подсчёт
- [fix_rshr_sleeper_counting](fix_rshr_sleeper_counting_d2cb8f75.plan.md) — подсчёт числа шпал, парковка вместо закрытия (INV-1/3)
- [rshr_screw_cycle_logic](rshr_screw_cycle_logic_93559ba6.plan.md) — логика циклов закрутки (INV-5)
- [rshr_offline_parity](rshr_offline_parity_1e366207.plan.md) — паритет offline/live, эталон 13 РШР / 1164 гайки
- [fsm_fix_+_monitor_export](fsm_fix_+_monitor_export_7741e103.plan.md) — фикс FSM + экспорт монитора
- [laser-false-trigger-guard](laser-false-trigger-guard_bcd08b06.plan.md) — защита от ложного лазера (INV-6)
- [fix_post2_length_corruption](fix_post2_length_corruption_ab5dac1d.plan.md) — коррупция длины на посту 2
- [проверка_данных_19.05](проверка_данных_19.05_06dc189e.plan.md) — валидация тестовых данных
- [rail_overhang](rail_overhang_0bb96d8b.plan.md) — забег рельсовых нитей из позиций торцов Sensor1 (INV-9, ADR-0010)

## Дашборд и UI
- [live_post2_dashboard_nuts](live_post2_dashboard_nuts_ab7884ff.plan.md) — live гайки ЛН/ЛВ/ПН/ПВ на дашборде
- [dashboard_camera_preview](dashboard_camera_preview_a437662e.plan.md) — превью камеры
- [dashboard_fixes_plan](dashboard_fixes_plan_df6f4a76.plan.md) — фиксы дашборда
- [editable_rshr_name](editable_rshr_name_c70427c8.plan.md) — редактирование номера РШР (scanned_name)
- [per-rail_r_t_stats](per-rail_r_t_stats_1c471824.plan.md) — статистика R/T по рельсе

## Отбраковка
- [отбраковка_операций](отбраковка_операций_a33145a3.plan.md) — UI + backend отбраковки операций
- [manual_reject_as_discard](manual_reject_as_discard_bd41a7ce.plan.md) — ручная отбраковка как discard

## Деплой и OCR
- [deploy_watermark_fix (1e9121bb)](deploy_watermark_fix_1e9121bb.plan.md) / [(dcbb83b1)](deploy_watermark_fix_dcbb83b1.plan.md) — деплой фикса watermark (INV-4)
- [ocr_train_and_deploy](ocr_train_and_deploy_4146d1f6.plan.md) — обучение и внедрение OCR номера РШР (вне runtime)
