import sys, copy, math, time, pdb, warnings, traceback
import os.path
import random
import argparse
from shutil import copy, rmtree, copytree
import torch
import numpy as np
from data_preprocess import *
from util_functions import *
from models import *
from train import *



# used to traceback which code cause warnings, can delete
def warn_with_traceback(message, category, filename, lineno, file=None, line=None):

    log = file if hasattr(file,'write') else sys.stderr
    traceback.print_stack(file=log)
    log.write(warnings.formatwarning(message, category, filename, lineno, line))

warnings.showwarning = warn_with_traceback


def logger(info, model, optimizer):
    epoch, train_loss, test_rmse = info['epoch'], info['train_loss'], info['test_rmse']
    with open(os.path.join(args.res_dir, 'log1.txt'), 'a') as f:
        f.write('Epoch {}, train loss {:.4f}, test rmse {:.6f}\n'.format(
            epoch, train_loss, test_rmse))
    if type(epoch) == int and epoch % args.save_interval == 0:
        print('Saving model states...')
        model_name = os.path.join(args.res_dir, 'model_checkpoint{}.pth'.format(epoch))
        optimizer_name = os.path.join(
            args.res_dir, 'optimizer_checkpoint{}.pth'.format(epoch)
        )
        if model is not None:
            torch.save(model.state_dict(), model_name)
        if optimizer is not None:
            torch.save(optimizer.state_dict(), optimizer_name)

if __name__ == '__main__':

    # Arguments
    parser = argparse.ArgumentParser(description='Inductive Graph-based Matrix Completion')
    # general settings
    parser.add_argument('--testing', action='store_true', default=True,
                        help='if set, use testing mode which splits all ratings into train/test;\
                        otherwise, use validation model which splits all ratings into \
                        train/val/test and evaluate on val only')
    parser.add_argument('--no-train', action='store_true', default=False,
                        help='if set, skip the training and directly perform the \
                        transfer/ensemble/visualization')
    parser.add_argument('--debug', action='store_true', default=True,
                        help='turn on debugging mode which uses a small number of data')
    parser.add_argument('--data-name', default='yahoo_music', help='dataset name')  # douban\yahoo_music\ml_100k\ml_1m
    # parser.add_argument('--data-name', default='ml_1m', help='dataset name')
    parser.add_argument('--data-appendix', default='_mnph100',
                        help='what to append to save-names when saving datasets')
    parser.add_argument('--save-appendix', default='_mnhp100',
                        help='what to append to save-names when saving results_d_30b_32dim')
    parser.add_argument('--max-train-num', type=int, default=None,
                        help='set maximum number of train data to use')
    parser.add_argument('--max-val-num', type=int, default=None,
                        help='set maximum number of val data to use')
    parser.add_argument('--max-test-num', type=int, default=None,
                        help='set maximum number of test data to use')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--data-seed', type=int, default=1234, metavar='S',
                        help='seed to shuffle data (1234,2341,3412,4123,1324 are used), \
                        valid only for ml_1m and ml_10m')
    parser.add_argument('--reprocess', action='store_true', default=False,
                        help='if True, reprocess data instead of using prestored .pkl data')
    parser.add_argument('--dynamic-test', action='store_true', default=True)
    parser.add_argument('--dynamic-val', action='store_true', default=True)
    parser.add_argument('--keep-old', action='store_true', default=False,
                        help='if True, do not overwrite old .py files in the result folder')
    parser.add_argument('--save-interval', type=int, default=5,
                        help='save model states every # epochs ')
    # subgraph extraction settings
    parser.add_argument('--hop', default=1, metavar='S',
                        help='enclosing subgraph hop number')
    parser.add_argument('--sample-ratio', type=float, default=1.0,
                        help='if < 1, subsample nodes per hop according to the ratio')
    parser.add_argument('--max-nodes-per-hop', default=100,
                        help='if > 0, upper bound the # nodes per hop by another subsampling')
    # edge dropout settings
    parser.add_argument('--adj-dropout', type=float, default=0,
                        help='if not 0, random drops edges from adjacency matrix with this prob')
    parser.add_argument('--force-undirected', action='store_true', default=False,
                        help='in edge dropout, force (x, y) and (y, x) to be dropped together')
    # optimization settings
    parser.add_argument('--continue-from', type=int, default=None,
                        help="from which epoch's checkpoint to continue training")
    parser.add_argument('--lr', type=float, default=1e-3, metavar='LR',
                        help='learning rate (default: 1e-3)')
    parser.add_argument('--lr-decay-step-size', type=int, default=20,
                        help='decay lr by factor A every B steps')
    parser.add_argument('--lr-decay-factor', type=float, default=0.1,
                        help='decay lr by factor A every B steps')
    parser.add_argument('--epochs', type=int, default=80, metavar='N',
                        help='number of epochs to train')
    parser.add_argument('--batch-size', type=int, default=50, metavar='N',
                        help='batch size during training')
    parser.add_argument('--test-freq', type=int, default=3, metavar='N',
                        help='test every n epochs')
    # transfer learning, ensemble, and visualization settings
    parser.add_argument('--transfer', default='',
                        help='if not empty, load the pretrained models in this path')
    parser.add_argument('--num-relations', type=int, default=5,
                        help='if transfer, specify num_relations in the transferred model')
    parser.add_argument('--multiply-by', type=int, default=1,
                        help='if transfer, specify how many times to multiply the predictions by')
    parser.add_argument('--visualize', action='store_true', default=False,
                        help='if True, load a pretrained model and do visualization exps')
    parser.add_argument('--ensemble', action='store_true', default=True,
                        help='if True, load a series of model checkpoints and ensemble the results_d_30b_32dim')
    parser.add_argument('--standard-rating', action='store_true', default=False,
                        help='if True, maps all ratings to standard 1, 2, 3, 4, 5 before training')
    # sparsity experiment settings
    parser.add_argument('--ratio', type=float, default=1.0,
                        help="For ml datasets, if ratio < 1, downsample training data to the\
                        target ratio")
    parser.add_argument('--subgraph-num',type=int,default=5,
                        help= "number of subgrphs for each (u,v) after cluster")
    parser.add_argument('--eps', type=int, default=0.9,
                        help="Eps-neighborhood of a point of the DBSCAN ")
    parser.add_argument('--cluster-samples', type=int, default=20,
                        help="cluster_samples")

    '''
        Set seeds, prepare for transfer learning (if --transfer)
    '''
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    print(args)

    # --max-nodes-per-hop, default=100,if > 0, upper bound the # nodes per hop by another subsampling
    args.hop = int(args.hop)
    if args.max_nodes_per_hop is not None:
        args.max_nodes_per_hop = int(args.max_nodes_per_hop)

    rating_map, post_rating_map = None, None
    if args.standard_rating:
        if args.data_name == 'yahoo_music':  # original 1, 2, ..., 100
            rating_map = {x: (x-1)//20+1 for x in range(1, 101)}
        else:
            rating_map = None
    # '--transfer', default='',help='if not empty, load the pretrained models in this path'
    if args.transfer:
        if args.data_name == 'yahoo_music':  # original 1, 2, ..., 100
            post_rating_map = {
                x: int(i // (100 / args.num_relations))
                for i, x in enumerate(np.arange(1, 101).tolist())
            }
        else:  # assume other datasets have standard ratings 1, 2, 3, 4, 5
            post_rating_map = {
                x: int(i // (5 / args.num_relations))
                for i, x in enumerate(np.arange(1, 6).tolist())
            }

    '''
        Prepare train/test (testmode) or train/val/test (valmode) splits
    '''
    # testing=True
    if args.testing:
        val_test_appendix = 'testmode'
    else:
        val_test_appendix = 'valmode'
    date_time = time.strftime("%Y_%m_%d")
    args.file_dir = os.path.dirname(os.path.realpath('__file__'))
    args.res_dir = os.path.join(
        args.file_dir, 'results/{}_{}_{}'.format(
            date_time, args.data_name, val_test_appendix
        )
    )

    if args.transfer == '':
        args.model_pos = os.path.join(args.res_dir, 'model_checkpoint{}.pth'.format(args.epochs))
    else:
        # if transfer is not empty,load the pretrained models in this path
        args.model_pos = os.path.join(args.transfer, 'model_checkpoint{}.pth'.format(args.epochs))
    if not os.path.exists(args.res_dir):
        os.makedirs(args.res_dir)

    if not args.keep_old and not args.transfer:
        # backup current main.py, model.py files
        copy('Main.py', args.res_dir)
        copy('util_functions.py', args.res_dir)
        copy('models.py', args.res_dir)
        copy('train.py', args.res_dir)


    if args.data_name == 'ml_1m':
        datasplit_path = (
            'raw_data/' + args.data_name + '/split_seed' + str(args.data_seed) +
            '.pickle'
        )
    else:
        datasplit_path = 'raw_data/' + args.data_name + '/nofeatures.pickle'
    # if args.data_name in ['musical_instruments', "books"]:
    #     (
    #         adj_train, train_labels, train_u_indices, train_v_indices,
    #         val_labels, val_u_indices, val_v_indices, test_labels, test_u_indices,
    #         test_v_indices, class_values, timestamp_mx_train, num_users, num_items
    #     ) = create_trainvaltest_split(
    #         args.data_name, 1234, args.testing, datasplit_path, True, True, rating_map,
    #         post_rating_map, args.ratio
    #     )
    if args.data_name in ['douban', 'yahoo_music']:
        (
            u_features, v_features, adj_train, train_labels, train_u_indices, train_v_indices,
            val_labels, val_u_indices, val_v_indices, test_labels, test_u_indices,
            test_v_indices, class_values
        ) = load_data_monti(args.data_name, args.testing, rating_map, post_rating_map)
    elif args.data_name == 'ml_100k':
        print("Using official MovieLens split u1.base/u1.test with 20% validation...")
        (
            u_features, v_features, adj_train,timestamp_mx_train, train_labels, train_u_indices, train_v_indices,
            val_labels, val_u_indices, val_v_indices, test_labels, test_u_indices,
            test_v_indices, class_values,num_users,num_items
        ) = load_official_trainvaltest_split(
            args.data_name, args.testing, rating_map, post_rating_map, args.ratio
        )
    else:
        (
            adj_train, train_labels, train_u_indices, train_v_indices,
            val_labels, val_u_indices, val_v_indices, test_labels, test_u_indices,
            test_v_indices, class_values, timestamp_mx_train, num_users, num_items
        ) = create_trainvaltest_split(
            args.data_name, 1234, args.testing, datasplit_path, True, True, rating_map,
            post_rating_map, args.ratio
        )
    print('All ratings are:')
    print(class_values)
    if args.debug:  # use a small number of data to debug
        num_data = 1000
        train_u_indices, train_v_indices = train_u_indices[:num_data], train_v_indices[:num_data]
        val_u_indices, val_v_indices = val_u_indices[:num_data], val_v_indices[:num_data]
        test_u_indices, test_v_indices = test_u_indices[:num_data], test_v_indices[:num_data]
    train_u_indices_set = set(train_u_indices)
    # train_v_indices_set = set(train_v_indices)
    test_u_indices_set = set(test_u_indices)
    # test_v_indices_set = set(test_v_indices)
    test1 =list(train_u_indices_set&test_u_indices_set)
    # test2 = list(train_v_indices_set&test_v_indices_set)
    #
    # print(list(train_u_indices_set&test_u_indices_set))
    # print(list(train_v_indices_set&test_v_indices_set))
    train_indices = (train_u_indices, train_v_indices)
    val_indices = (val_u_indices, val_v_indices)
    test_indices = (test_u_indices, test_v_indices)
    print('#train: %d, #val: %d, #test: %d' % (
        len(train_u_indices),
        len(val_u_indices),
        len(test_u_indices),
    ))

    # 一阶邻居的平均长度统计
    Arow = SparseRowIndexer(adj_train)
    Acol = SparseColIndexer(adj_train.tocsc())

    num_centre = len(train_u_indices)
    num_neibhors = []
    num_u_neighbors= []
    for idx in range(num_centre):
        u_,v_ = train_indices[0][idx],train_indices[1][idx]

        v_fringe,u_fringe = neighbors(set([u_]),Arow),neighbors(set([v_]),Acol)
        u_fringe = u_fringe-set([u_])
        v_fringe = v_fringe-set([v_])
        num_u_neighbors.append(len(v_fringe))
        num_neibhor = len(u_fringe)+len(v_fringe)
        num_neibhors.append(num_neibhor)
    avg_u_neighbor = sum(num_u_neighbors)/len(num_u_neighbors)
    avg_train = sum(num_neibhors)/len(num_neibhors)

    num_centre_test = len(test_u_indices)
    num_neibhors_test = []
    num_u_neighbor_test = []
    for idx in range(num_centre_test):
        u_,v_ = test_indices[0][idx],test_indices[1][idx]
        v_fringe,u_fringe = neighbors(set([u_]),Arow),neighbors(set([v_]),Acol)
        u_fringe = u_fringe-set([u_])
        v_fringe = v_fringe-set([v_])
        num_u_neighbor_test.append(len(v_fringe))
        num_neibhor = len(u_fringe)+len(v_fringe)
        num_neibhors_test.append(num_neibhor)
    avg_test = sum(num_neibhors_test)/len(num_neibhors_test)
    avg_u_neighbor_test = sum(num_u_neighbor_test)/len(num_u_neighbor_test)
    avg_u_neighbors = (avg_u_neighbor+avg_u_neighbor_test)/2
    avg = (avg_test+avg_train)/2

    u_neighbors_list = num_u_neighbors+num_u_neighbor_test
    with open("list.txt",'a') as f:
        f.write(args.data_name+":")
        f.write("\n")
        f.write(str(u_neighbors_list))
        f.write("\n")
    if args.data_name == "yahoo_music":
        dic = {
            "[0,5)":0,
            "[5,10)":0,
            "[10,15)":0,
            "[15,20)":0,
            "[20,":0
        }
        for i in u_neighbors_list:
            if i<5:
                dic["[0,5)"]+=1
            elif 5<=i<10:
                dic["[5,10)"]+=1
            elif 10<=i<15:
                dic["[10,15)"]+=1
            elif 15<=i<20:
                dic["[15,20)"]+=1
            else:
                dic["[20,"]+=1
    if args.data_name =="douban":
        dic = {
            "[0,20)": 0,
            "[20,40)": 0,
            "[40,60)": 0,
            "[60,)": 0,
        }
        for i in u_neighbors_list:
            if i < 20:
                dic["[0,20)"] += 1
            elif 20 <= i < 40:
                dic["[20,40)"] += 1
            elif 40 <= i < 60:
                dic["[40,60)"] += 1
            else:
                dic["[60,)"] += 1
    if args.data_name =="ml_100k":
        dic = {
            "[0,10)": 0,
            "[10,30)":0,
            "[30,50)":0,
            "[50,100)":0,
            "[100,200)": 0,
            "[200,300)": 0,
            "[300,400)":0,
            "[400":0
        }
        for i in u_neighbors_list:
            if i < 10:
                dic["[0,10)"] += 1
            if 10<=i < 30:
                dic["[10,30)"] += 1
            if 30<=i < 50:
                dic["[30,50)"] += 1
            if 50<=i < 100:
                dic["[50,100)"] += 1
            elif 100 <= i < 200:
                dic["[100,200)"] += 1
            elif 200 <= i < 300:
                dic["[200,300)"] += 1
            elif 300 <= i < 400:
                dic["[300,400)"] += 1
            else:
                dic["[400"]+=1
    if args.data_name =="ml_1m":
        dic = {
            "[0,100)": 0,
            "[100,200)": 0,
            "[200,300)": 0,
            "[300,400)": 0,
            "[400,500)": 0,
            "[500":0
        }
        for i in u_neighbors_list:
            if i < 100:
                dic["[0,100)"] += 1
            elif 100 <= i < 200:
                dic["[100,200)"] += 1
            elif 200 <= i < 300:
                dic["[200,300)"] += 1
            elif 300 <= i < 400:
                dic["[300,400)"] += 1
            elif 400 <= i < 500:
                dic["[400,500)"] += 1
            else:
                dic["[500"] += 1

    '''
           Extract enclosing subgraphs to build the train/test or train/val/test graph datasets.
           (Note that we must extract enclosing subgraphs for testmode and valmode separately, 
           since the adj_train is different.)
       '''
    train_graphs, val_graphs, test_graphs = None, None, None
    data_combo = (args.data_name, args.data_appendix, val_test_appendix)
    if args.reprocess:  # False
        # if reprocess=True, delete the previously cached data and reprocess.
        if os.path.isdir('data/{}{}/{}/train'.format(*data_combo)):
            rmtree('data/{}{}/{}/train'.format(*data_combo))
        if os.path.isdir('data/{}{}/{}/val'.format(*data_combo)):
            rmtree('data/{}{}/{}/val'.format(*data_combo))
        if os.path.isdir('data/{}{}/{}/test'.format(*data_combo)):
            rmtree('data/{}{}/{}/test'.format(*data_combo))
    u_features = None
    v_features = None
    train_graphs = MyDynamicDataset(
        'data/{}{}/{}/train'.format(*data_combo),
        adj_train,  # {narray:(6040，3706)},一共6040个用户，3706个电影。存储的是训练数据，即训练用户对item的评分1-5
        timestamp_mx_train,
        train_indices,  # {tuple:2},(train_u_indices,train_v_indices),({ndarray:(900188,)},{ndarray:(900188,)})
        train_labels,  # {ndarray:(900188)},0-4
        args.hop,  # 1
        args.sample_ratio,  # 1.0
        args.subgraph_num,
        args.eps,
        args.cluster_samples,
        args.max_nodes_per_hop,  # 100
        u_features,  # None
        v_features,  # None
        class_values,  # [1,2,3,4,5]
        max_num=args.max_train_num  # None
    )

    test_graphs = MyDynamicDataset(
        'data/{}{}/{}/test'.format(*data_combo),
        adj_train,  # {narray:(6040，3706）},存储的是训练数据，即训练用户对item的评分1-5
        timestamp_mx_train,
        test_indices,  # {tuple:2}, (test_u_indices, test_v_indices),({ndarray:(100021,)},{ndarray:(100021,)})
        test_labels,  # {narray:(100021,)},[3,2,2,4,3,0,.......]
        args.hop,  # 1
        args.sample_ratio,  # 1.0
        args.subgraph_num,
        args.eps,
        args.cluster_samples,
        args.max_nodes_per_hop,  # 100
        u_features,  # None
        v_features,  # None
        class_values,  # [1,2,3,4,5]
        max_num=args.max_test_num  # None
    )

    if not args.testing:
        dataset_class = 'MyDynamicDataset' if args.dynamic_val else 'MyDataset'
        val_graphs = eval(dataset_class)(
            'data/{}{}/{}/val'.format(*data_combo),
            adj_train,
            timestamp_mx_train,
            val_indices,
            val_labels,
            args.hop,
            args.sample_ratio,
            args.subgraph_num,
            args.eps,
            args.cluster_samples,
            args.max_nodes_per_hop,
            u_features,
            v_features,
            class_values,
            max_num=args.max_val_num
        )
    if not args.testing:
        test_graphs = val_graphs

    print('Used #train graphs: %d, #test graphs: %d' % (
        len(train_graphs),  # 900188个user个item的交互，900188条边
        len(test_graphs),  # 100021
    ))
    if args.transfer:
        num_relations = args.num_relations
        multiply_by = args.multiply_by
    else:
        num_relations = len(class_values)  # 5
        multiply_by = 1

    model = IGMC(
        train_graphs,
        num_users,
        num_items,
        latent_dim=[32, 32, 32, 32],
        num_relations=num_relations,  # 5
        num_bases=4,
        regression=True,
        adj_dropout=args.adj_dropout,  # 0.0
        force_undirected=args.force_undirected,  # False
        side_features=False,  # false,不用side information
        n_side_features=0,  # 0
        multiply_by=multiply_by,  # 1
    )
    total_params = sum(p.numel() for param in model.parameters() for p in param)
    print(f'Total number of parameters is {total_params}')

    if not args.no_train:
        train_multiple_epochs(
            train_graphs,
            test_graphs,
            model,
            args.epochs,
            args.batch_size,
            args.lr,
            lr_decay_factor=args.lr_decay_factor,
            lr_decay_step_size=args.lr_decay_step_size,
            weight_decay=0,
            test_freq=args.test_freq,
            logger=logger,
            continue_from=args.continue_from,  # None
            res_dir=args.res_dir
        )
        if args.visualize:
            model.load_state_dict(torch.load(args.model_pos))
            visualize(
                model,
                test_graphs,
                args.res_dir,
                args.data_name,
                class_values,
                sort_by='prediction'
            )
            if args.transfer:
                rmse = test_once(test_graphs, model, args.batch_size, logger)
                print('Transfer learning rmse is: {:.6f}'.format(rmse))
        else:
            if args.ensemble:
                if args.data_name == 'ml_1m':
                    start_epoch, end_epoch, interval = 5, args.epochs, 5
                    # start_epoch, end_epoch, interval = args.epochs , args.epochs, 5
                else:
                    start_epoch, end_epoch, interval = args.epochs - 30, args.epochs, 10
                if args.transfer:
                    checkpoints = [
                        os.path.join(args.transfer, 'model_checkpoint%d.pth' % x)
                        for x in range(start_epoch, end_epoch + 1, interval)
                    ]
                    epoch_info = 'transfer {}, ensemble of range({}, {}, {})'.format(
                        args.transfer, start_epoch, end_epoch, interval
                    )
                else:
                    checkpoints = [
                        os.path.join(args.res_dir, 'model_checkpoint%d.pth' % x)
                        for x in range(start_epoch, end_epoch + 1, interval)
                    ]
                    epoch_info = 'ensemble of range({}, {}, {})'.format(
                        start_epoch, end_epoch, interval
                    )
                rmse = test_once(
                    test_graphs,
                    model,
                    args.batch_size,
                    logger=None,
                    ensemble=True,
                    checkpoints=checkpoints
                )
                print('Ensemble test rmse is: {:.6f}'.format(rmse))
            else:
                if args.transfer:
                    model.load_state_dict(torch.load(args.model_pos))
                    rmse = test_once(test_graphs, model, args.batch_size, logger=None)
                    epoch_info = 'transfer {}, epoch {}'.format(args.transfer, args.epoch)
                print('Test rmse is: {:.6f}'.format(rmse))

            eval_info = {
                'epoch': epoch_info,
                'train_loss': 0,
                'test_rmse': rmse,
            }
            logger(eval_info, None, None)


