import type { DatasetTable } from '../api/types.ts'

/**
 * Tables shaped like real backend output (every cell a string, messy on purpose) for tests and for
 * previewing the dashboard without a live scrape. Fictional values; sources use .example domains.
 */
export const evSales: DatasetTable = {
  name: 'EV sales by month',
  source_url: 'https://vahan.example/ev',
  columns: ['Month', 'Year', 'EV Units Sold', 'Source'],
  rows: [
    ['January', '2024', '1,44,879', 'https://vahan.example/ev'],
    ['February', '2024', '1,41,382', 'https://vahan.example/ev'],
    ['March', '2024', '2,13,062', 'https://vahan.example/ev'],
    ['April', '2024', '1,15,297', 'https://vahan.example/ev'],
    ['May', '2024', '1,39,275', 'https://vahan.example/ev'],
    ['June', '2024', 'N/A', 'https://vahan.example/ev'],
    ['January', '2025', '1,72,106', 'https://autodata.example/ev'],
    ['February', '2025', '1,58,847', 'https://autodata.example/ev'],
    ['March', '2025', '2,31,540', 'https://autodata.example/ev'],
  ],
  row_count: 9,
}

export const evCars: DatasetTable = {
  name: 'Electric cars under 20 lakh',
  source_url: 'https://cars.example/ev',
  columns: ['model', 'brand', 'price_inr', 'range_km', 'body_type', 'launch_date'],
  rows: [
    ['Nexon EV', 'Tata', '₹12.49 Lakh', '465 km', 'SUV', '14/09/2023'],
    ['Punch EV', 'Tata', '₹ 9,99,000', '421 km', 'SUV', '17/01/2024'],
    ['Tiago EV', 'Tata', 'Rs. 7.99 lakh', '315 km', 'Hatchback', '28/09/2022'],
    ['ZS EV', 'MG', '₹18.98 Lakh', '461 km', 'SUV', '07/03/2022'],
    ['Comet EV', 'MG', '₹6.99 Lakh', '230 km', 'Hatchback', '26/04/2023'],
    ['XUV400', 'Mahindra', '₹15.49 Lakh', '456 km', 'SUV', '16/01/2023'],
    ['eC3', 'Citroen', '₹11.61 Lakh', '320 km', 'Hatchback', '28/02/2023'],
    ['Windsor EV', 'MG', 'N/A', '331 km', 'Crossover', '11/09/2024'],
    ['Creta EV', 'Hyundai', '₹17.99 Lakh', '473 km', 'SUV', '17/01/2025'],
    ['Tigor EV', 'tata ', '₹12.49 Lakh', '315 km', 'Sedan', '31/08/2021'],
  ],
  row_count: 10,
}
