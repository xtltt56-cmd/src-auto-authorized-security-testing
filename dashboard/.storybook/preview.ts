import type { Preview } from '@storybook/react-vite'
import '../src/styles/global.css'

const preview: Preview = {
  parameters: {
    controls: { expanded: true },
    a11y: { test: 'error' },
    backgrounds: {
      default: 'surface',
      values: [{ name: 'surface', value: '#F7FAFC' }],
    },
  },
}

export default preview
