declare module 'react-simple-maps' {
  import { ComponentType, SVGProps } from 'react';

  export const ComposableMap: ComponentType<{
    projection?: string;
    projectionConfig?: Record<string, unknown>;
    style?: React.CSSProperties;
    children?: React.ReactNode;
  }>;

  export const ZoomableGroup: ComponentType<{
    zoom?: number;
    maxZoom?: number;
    children?: React.ReactNode;
  }>;

  export const Geographies: ComponentType<{
    geography: string;
    children: (props: { geographies: Array<{ rsmKey: string; properties: Record<string, unknown> }> }) => React.ReactNode;
  }>;

  export const Geography: ComponentType<{
    geography: Record<string, unknown>;
    fill?: string;
    stroke?: string;
    strokeWidth?: number;
    style?: {
      default?: React.CSSProperties;
      hover?: React.CSSProperties;
      pressed?: React.CSSProperties;
    };
  }>;

  export const Marker: ComponentType<{
    coordinates: [number, number];
    children?: React.ReactNode;
  }>;
}
