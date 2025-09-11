import clsx from 'clsx';
import styles from './styles.module.css';

const FeatureList = [
  {
    title: '🎯 One Command Benchmarking',
    Svg: require('@site/static/img/deploy-benchmark.svg').default,
    description: (
      <>
        Deploy → Benchmark → Report in a single command. Get comprehensive
        metrics including p95 latency, cost per 1K tokens, and energy consumption
        with professional output formats.
      </>
    ),
  },
  {
    title: '⚡ Advanced vLLM Features',
    Svg: require('@site/static/img/vllm-features.svg').default,
    description: (
      <>
        Test speculative decoding, quantization (AWQ/GPTQ/FP8), structured outputs,
        and tool calling with ready-to-use profiles. Measure real performance impact
        of cutting-edge vLLM capabilities.
      </>
    ),
  },
  {
    title: '🔍 Backend Comparison',
    Svg: require('@site/static/img/backend-comparison.svg').default,
    description: (
      <>
        Automated vLLM vs TGI vs TensorRT-LLM comparison with HTML reports.
        Make data-driven decisions about inference runtime selection with
        objective performance metrics.
      </>
    ),
  },
];

function Feature({Svg, title, description}) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} role="img" />
      </div>
      <div className="text--center padding-horiz--md">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
