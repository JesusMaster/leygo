import { Pipe, PipeTransform, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';

@Pipe({
  name: 'markdown',
  standalone: true
})
export class MarkdownPipe implements PipeTransform {
  private sanitizer = inject(DomSanitizer);

  transform(value: string): SafeHtml {
    if (!value) return '';
    
    let processedValue = value;
    
    // Auto-convert QuickChart URLs to images if sent as raw URLs or standard links.
    processedValue = processedValue.replace(/(?<!\!)\[([^\]]+)\]\((https:\/\/quickchart\.io\/chart\?[^\)]+)\)/g, '![$1]($2)');
    processedValue = processedValue.replace(/(?<!\()https:\/\/quickchart\.io\/chart\?[^\s<]+/g, (match) => `![](${match})`);
    
    // Convert markdown to HTML (Default marked.parse is synchronous)
    const html = marked.parse(processedValue, { async: false }) as string;
    
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
