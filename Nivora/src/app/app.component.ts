import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, ViewChild } from '@angular/core';
import { ThreeCanvasComponent } from './three-canvas.component';
import { BatteryDashboardComponent } from './battery-dashboard.component';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ThreeCanvasComponent, BatteryDashboardComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements AfterViewInit {
  @ViewChild('modelStage', { static: false }) modelStage?: ElementRef<HTMLElement>;

  activeView: 'full' | 'hmi-only' = 'full';

  ngAfterViewInit(): void {
    this.initGsapAnimations();
  }

  private initGsapAnimations(): void {
    if (this.modelStage) {
      gsap.from('.hero-copy > *', { y: 24, opacity: 0, duration: 0.85, stagger: 0.1, ease: 'power3.out', delay: 0.25 });
      gsap.from('.metric-card', { y: 18, opacity: 0, duration: 0.8, stagger: 0.12, ease: 'power3.out', delay: 0.55 });
      gsap.to('.hero-copy', {
        yPercent: -18,
        opacity: 0.15,
        scrollTrigger: { trigger: '.hero', start: 'top top', end: '+=80%', scrub: true }
      });
      gsap.to(this.modelStage.nativeElement, {
        scale: 1.25,
        yPercent: 9,
        scrollTrigger: { trigger: '.hero', start: 'top top', end: '+=115%', scrub: true }
      });
    }
  }

  scrollToHmi(): void {
    if (this.activeView === 'hmi-only') {
      return;
    }
    const elem = document.querySelector('#battery-hmi-section');
    if (elem) {
      elem.scrollIntoView({ behavior: 'smooth' });
    }
  }

  switchToHmiOnly(): void {
    this.activeView = 'hmi-only';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  switchToFullView(): void {
    this.activeView = 'full';
    setTimeout(() => {
      this.initGsapAnimations();
    }, 100);
  }
}

