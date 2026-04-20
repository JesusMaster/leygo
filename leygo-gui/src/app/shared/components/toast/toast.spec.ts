import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { ToastComponent } from './toast';
import { ToastService } from '@services/toast.service';
import { Subject } from 'rxjs';

describe('ToastComponent', () => {
    let component: ToastComponent;
    let fixture: ComponentFixture<ToastComponent>;
    let toastSubject: Subject<any>;
    let toastServiceMock: any;

    beforeEach(() => {
        toastSubject = new Subject();
        toastServiceMock = { toastState: toastSubject.asObservable() };

        TestBed.configureTestingModule({
            imports: [ToastComponent],
            providers: [{ provide: ToastService, useValue: toastServiceMock }]
        });

        fixture = TestBed.createComponent(ToastComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });

    it('should show toast and auto-remove after delay', fakeAsync(() => {
        const toast = { type: 'success' as const, message: 'ok', position: 'top-right' as const, delay: 100 };
        toastSubject.next(toast);
        expect(component.toastGroups['top-right'].length).toBe(1);
        tick(100);
        expect(component.toastGroups['top-right'].length).toBe(0);
    }));

    it('should remove toast manually', () => {
        const toast = { type: 'info' as const, message: 'hi', position: 'bottom-left' as const, delay: 5000 };
        toastSubject.next(toast);
        component.removeToast(toast);
        expect(component.toastGroups['bottom-left'].length).toBe(0);
    });

    it('should remove toast manually with fallback position', () => {
        const toast = { type: 'info' as const, message: 'hi' } as any; // No position
        toastSubject.next(toast);
        component.removeToast(toast);
        expect(component.toastGroups['top-right'].length).toBe(0);
    });

    it('should use default position top-right if none specified', fakeAsync(() => {
        const toast = { type: 'info' as const, message: 'default' } as any;
        toastSubject.next(toast);
        expect(component.toastGroups['top-right']).toBeDefined();
        tick(5000); // Should use default 5000 delay
        expect(component.toastGroups['top-right'].length).toBe(0);
    }));

    it('should return objectKeys', () => {
        const keys = component.objectKeys({ a: 1, b: 2 });
        expect(keys).toEqual(['a', 'b']);
    });

    it('should return correct icon class', () => {
        expect(component.getIconClass('success')).toContain('check');
        expect(component.getIconClass('info')).toContain('info');
        expect(component.getIconClass('warning')).toContain('exclamation-triangle');
        expect(component.getIconClass('danger')).toContain('exclamation-circle');
        expect(component.getIconClass('unknown')).toContain('info');
    });

    it('should return correct toast class', () => {
        expect(component.getToastClass('success')).toContain('green');
        expect(component.getToastClass('info')).toContain('blue');
        expect(component.getToastClass('warning')).toContain('yellow');
        expect(component.getToastClass('danger')).toContain('red');
        expect(component.getToastClass('unknown')).toContain('blue');
    });
});
