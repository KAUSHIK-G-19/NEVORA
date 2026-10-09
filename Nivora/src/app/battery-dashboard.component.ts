import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';

export interface BatteryCell {
  id: number;
  moduleId: string;
  voltage: number;
  temp: number;
  impedance: number;
  soh: number;
  balancing: boolean;
  status: 'optimal' | 'warning' | 'critical';
}

export type DriveMode = 'charge' | 'drive' | 'ludicrous' | 'regen' | 'balance';

declare global {
  interface Window {
    angular?: any;
    nevoraAngularBridge?: any;
  }
}

@Component({
  selector: 'app-battery-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './battery-dashboard.component.html',
  styleUrl: './battery-dashboard.component.css'
})
export class BatteryDashboardComponent implements OnInit, OnDestroy {
  // Master Battery Telemetry
  soc: number = 84.6; // State of charge %
  packVoltage: number = 401.8; // Volts
  packCurrent: number = -24.8; // Amperes (negative = discharge, positive = charge)
  packTemp: number = 31.4; // Celsius
  soh: number = 98.4; // State of health %
  rulCycles: number = 1240; // Remaining useful life in cycles
  degradationRisk: number = 0.04; // 0.0 to 1.0
  pinnLatency: number = 4.2; // ms
  pinnLoss: number = 0.00012;
  coolantFlow: number = 14.5; // L/min

  // Energy & Range calculations
  totalCapacityKwh: number = 100.0;
  get currentKwh(): number {
    return Number(((this.soc / 100) * this.totalCapacityKwh).toFixed(1));
  }
  get estimatedRangeKm(): number {
    return Math.round((this.soc / 100) * 580);
  }
  get powerKw(): number {
    return Number(((this.packVoltage * this.packCurrent) / 1000).toFixed(1));
  }

  // Operating State
  currentMode: DriveMode = 'drive';
  isFaultInjected: boolean = false;
  activeModuleFilter: string = 'ALL';
  selectedCell: BatteryCell | null = null;
  angularJsVersion: string = '1.8.3';
  angularVersion: string = '21.0.0';
  rawCanPackets: Array<{ id: string; dlc: number; data: string; time: string; type: string }> = [];

  // 32-Cell Battery Matrix
  cells: BatteryCell[] = [];

  private timerInterval: any = null;
  private canLogInterval: any = null;
  private tickCount: number = 0;

  ngOnInit(): void {
    this.initCells();
    this.initAngularJsBridge();
    this.startTelemetryLoop();
    this.selectedCell = this.cells[13]; // Default preview
  }

  ngOnDestroy(): void {
    if (this.timerInterval) clearInterval(this.timerInterval);
    if (this.canLogInterval) clearInterval(this.canLogInterval);
  }

  private initCells(): void {
    const modules = ['MOD-A', 'MOD-B', 'MOD-C', 'MOD-D'];
    const cellList: BatteryCell[] = [];

    for (let i = 1; i <= 32; i++) {
      const modIndex = Math.floor((i - 1) / 8);
      // Nominal cell voltage between 4.10V and 4.16V
      const baseV = 4.12 + (Math.sin(i * 1.7) * 0.03);
      cellList.push({
        id: i,
        moduleId: modules[modIndex],
        voltage: Number(baseV.toFixed(3)),
        temp: Number((30.8 + (Math.cos(i) * 1.8)).toFixed(1)),
        impedance: Number((1.35 + (i % 5) * 0.05).toFixed(2)),
        soh: Number((98.2 + (Math.sin(i) * 0.6)).toFixed(1)),
        balancing: i % 4 === 0,
        status: 'optimal'
      });
    }
    this.cells = cellList;
  }

  private initAngularJsBridge(): void {
    if (typeof window !== 'undefined' && window.angular) {
      try {
        if (!window.angular.module('nevoraBatteryBridge', [])) {
          window.angular.module('nevoraBatteryBridge', []);
        }
        window.nevoraAngularBridge = {
          getTelemetry: () => ({
            soc: this.soc,
            packVoltage: this.packVoltage,
            packCurrent: this.packCurrent,
            packTemp: this.packTemp,
            soh: this.soh,
            rulCycles: this.rulCycles,
            degradationRisk: this.degradationRisk,
            mode: this.currentMode
          }),
          setMode: (mode: DriveMode) => this.setMode(mode),
          version: '1.8.3'
        };
      } catch (e) {
        console.warn('AngularJS bridge initialization note:', e);
      }
    }
  }

  setMode(mode: DriveMode): void {
    this.currentMode = mode;

    switch (mode) {
      case 'charge':
        this.packCurrent = +118.5; // DC Fast charge 120A
        break;
      case 'drive':
        this.packCurrent = -24.8; // Cruising
        break;
      case 'ludicrous':
        this.packCurrent = -186.2; // Launch mode
        break;
      case 'regen':
        this.packCurrent = +38.4; // Kinetic recovery
        break;
      case 'balance':
        this.packCurrent = -1.2; // Passive shunting
        break;
    }
  }

  toggleFaultInjection(): void {
    this.isFaultInjected = !this.isFaultInjected;
    const targetCell = this.cells.find(c => c.id === 14);

    if (this.isFaultInjected && targetCell) {
      targetCell.voltage = 3.38;
      targetCell.temp = 54.2;
      targetCell.status = 'critical';
      this.degradationRisk = 0.74;
      this.coolantFlow = 28.0; // Emergency max cooling
    } else if (targetCell) {
      targetCell.voltage = 4.11;
      targetCell.temp = 32.1;
      targetCell.status = 'optimal';
      this.degradationRisk = 0.04;
      this.coolantFlow = 14.5;
    }
  }

  selectCell(cell: BatteryCell): void {
    this.selectedCell = cell;
  }

  get filteredCells(): BatteryCell[] {
    if (this.activeModuleFilter === 'ALL') return this.cells;
    return this.cells.filter(c => c.moduleId === this.activeModuleFilter);
  }

  private startTelemetryLoop(): void {
    this.timerInterval = setInterval(() => {
      this.tickCount++;

      // Physics micro-oscillations based on mode
      if (this.currentMode === 'charge') {
        if (this.soc < 99.8) this.soc = Number((this.soc + 0.05).toFixed(2));
        this.packVoltage = Number((408.0 + Math.sin(this.tickCount * 0.2) * 1.5).toFixed(1));
        this.packTemp = Number(Math.min(38.0, this.packTemp + 0.02).toFixed(1));
      } else if (this.currentMode === 'drive') {
        if (this.soc > 2.0) this.soc = Number((this.soc - 0.02).toFixed(2));
        this.packVoltage = Number((401.5 + Math.sin(this.tickCount * 0.3) * 1.2).toFixed(1));
        this.packTemp = Number((31.4 + Math.sin(this.tickCount * 0.1) * 0.5).toFixed(1));
      } else if (this.currentMode === 'ludicrous') {
        if (this.soc > 2.0) this.soc = Number((this.soc - 0.08).toFixed(2));
        // Voltage sag under 180A load
        this.packVoltage = Number((384.2 + Math.sin(this.tickCount * 0.5) * 2.0).toFixed(1));
        this.packTemp = Number(Math.min(46.0, this.packTemp + 0.05).toFixed(1));
      } else if (this.currentMode === 'regen') {
        if (this.soc < 99.8) this.soc = Number((this.soc + 0.03).toFixed(2));
        this.packVoltage = Number((405.2 + Math.cos(this.tickCount * 0.4) * 1.0).toFixed(1));
      }

      // Micro-jitter cell voltages
      this.cells.forEach(c => {
        if (c.status !== 'critical') {
          const jitter = (Math.random() - 0.5) * 0.006;
          c.voltage = Number(Math.max(3.6, Math.min(4.2, c.voltage + jitter)).toFixed(3));
        }
      });

      // Update CAN bus log periodically
      if (this.tickCount % 2 === 0) {
        this.pushSimulatedCanFrame();
      }
    }, 1000);
  }

  private pushSimulatedCanFrame(): void {
    const now = new Date().toTimeString().split(' ')[0] + '.' + Math.floor(Math.random() * 900 + 100);
    const isVFrame = Math.random() > 0.5;

    if (isVFrame) {
      // 0x18F00101: Voltage & Current frame (from can_reader.cpp)
      const vHex = Math.round(this.packVoltage * 10).toString(16).padStart(8, '0').toUpperCase();
      const iHex = Math.round((this.packCurrent + 1000) * 10).toString(16).padStart(8, '0').toUpperCase();
      this.rawCanPackets.unshift({
        id: '0x18F00101',
        dlc: 8,
        data: `${vHex.slice(0, 4)} ${vHex.slice(4, 8)} ${iHex.slice(0, 4)} ${iHex.slice(4, 8)}`,
        time: now,
        type: 'V_I_TELEMETRY'
      });
    } else {
      // 0x18F00201: Temperature frame (from can_reader.cpp)
      const tHex = Math.round((this.packTemp + 40) * 10).toString(16).padStart(4, '0').toUpperCase();
      this.rawCanPackets.unshift({
        id: '0x18F00201',
        dlc: 2,
        data: `${tHex} 00 00`,
        time: now,
        type: 'THERMAL_STATE'
      });
    }

    if (this.rawCanPackets.length > 6) {
      this.rawCanPackets.pop();
    }
  }
}
