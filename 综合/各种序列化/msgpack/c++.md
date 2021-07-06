1.安装:
apt-get install libmsgpack-dev

会安装在/usr/lib/ 和 /usr/include 下  

2.基本使用:
  
  std::string path="...."
  myclass item {};
  //写入
  msgpack::sbuffer buffer_;
  msgpack::packer<msgpack::sbuffer>  pack(&buffer_);
  pack.pack(item);
  fstream myfile;
  myfile.open(path,ios::app|ios::binary|ios::out);
  myfile.write(buffer_.data(),buffer_.size());
  //读取
  fstream tmp_file ;
  tmp_file.open(path,ios::in|ios::binary);
  tmp_file.seekg(0,ios::end);
  auto length = tmp_file.tellg();
  tmp_file.seekg(0,ios::beg);
  msgpack::unpacker unpack;
  unpack.reserve_buffer(length);
  tmp_file.read(unpack.buffer(), length);
  unpack.buffer_consumed(length);
  msgpack::unpacked result;
  while(unpack.next(&result)){
    facerec::benchmarks::analyze::Item item;
    msgpack::object obj = result.get();
    myclass reslut;
    obj.convert(&reslut);
  }
  
  
  
  
  https://github.com/msgpack/msgpack-c/blob/master/QUICKSTART-CPP.md
