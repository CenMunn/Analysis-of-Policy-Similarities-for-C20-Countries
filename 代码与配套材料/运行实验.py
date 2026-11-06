"""统一入口。默认课堂模式复算五阶段；full重新逐段识别原文。"""
from pathlib import Path
import argparse,sys,time,json,traceback
from datetime import datetime
sys.dont_write_bytecode=True
from src.common import ROOT,write_json

def main():
    parser=argparse.ArgumentParser(description='第一组国家双碳政策分析')
    parser.add_argument('--mode',choices=['classroom','full'],default='classroom')
    parser.add_argument('--output',type=Path,help='新建目录；默认每次生成新的时间戳目录')
    parser.add_argument('--reencode-bge',action='store_true',help='实际调用本地BGE模型重新编码，可用GPU')
    args=parser.parse_args();out=args.output or ROOT/'演示输出'/datetime.now().strftime('%Y%m%d_%H%M%S')
    if out.exists():parser.error('输出目录已经存在，请选择新目录，避免覆盖证据。')
    out.mkdir(parents=True);log=[];start=time.perf_counter()
    from src.data_cleaning import run
    from src.text_features import run_features
    from src.word_vectors import run_vectors
    from src.country_analysis import run_countries
    from src.evaluation import run_evaluation
    from src.figures import make_figures
    from src.verification import verify,freeze
    stages=[('01 数据清洗',lambda:run(out,reuse=args.mode=='classroom')),
            ('02 统一分词与TF-IDF',lambda:run_features(out)),('03 加权词向量与BGE',lambda:run_vectors(out,args.reencode_bge)),
            ('04 国家与教师六组',lambda:run_countries(out)),('05 评价与词数实验',lambda:run_evaluation(out)),
            ('06 绘图',lambda:make_figures(out)),('07 核验',lambda:verify(out))]
    print('模式：'+args.mode+'；输出：'+str(out),flush=True)
    if args.mode=='classroom':
        print('课堂模式：重读原始ZIP；复用经校验的识别账本，重新计算规则末端、分词、权重、聚合及评价。',flush=True)
    print('BGE：'+('调用本地冻结模型重新推理' if args.reencode_bge else '按文本SHA复用核验过的冻结编码'),flush=True)
    try:
        for name,fn in stages:
            t=time.perf_counter();print('\n开始 '+name,flush=True);fn();elapsed=time.perf_counter()-t
            log.append(dict(stage=name,seconds=round(elapsed,3),passed=True));write_json(out/'核验/统一入口日志.json',log)
            print(f'完成 {name}：{elapsed:.1f} 秒',flush=True)
        write_json(out/'核验/本次运行.json',dict(mode=args.mode,bge_reencoded=args.reencode_bge,total_seconds=time.perf_counter()-start,version='G20-GROUP1-20261027.final'))
        freeze(out)
        print('\n全流程完成，核验通过：'+str(out),flush=True)
    except Exception:
        (out/'失败记录.txt').write_text(traceback.format_exc(),encoding='utf-8');raise

if __name__=='__main__':main()
